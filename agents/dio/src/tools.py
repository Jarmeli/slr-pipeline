"""DIO MCP Tools — Data Ingestion & Operations Agent."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow importing shared/ when running inside container
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.db import audit, get_pool
from shared.schemas import HandoffToken, TableInfo


# ── Tool implementations ──────────────────────────────────────────────────────

@audit("DIO")
async def list_raw_tables() -> List[Dict[str, str]]:
    """List all user tables in the public schema."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema IN ('public', 'clean_data')
            ORDER BY table_name
            """
        )
    return [dict(r) for r in rows]


@audit("DIO")
async def describe_table(table: str, schema: str = "public") -> Dict[str, Any]:
    """Return column metadata and approximate row count for a table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        cols = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position
            """,
            schema,
            table,
        )
        count_row = await conn.fetchrow(
            f'SELECT COUNT(*) AS n FROM "{schema}"."{table}"'
        )
    return {
        "table": table,
        "schema": schema,
        "columns": [dict(c) for c in cols],
        "row_count": count_row["n"],
    }


@audit("DIO")
async def get_table_extent(table: str, schema: str = "public") -> Dict[str, Any]:
    """Calculate the spatial bounding box (extent) of a table's geometry column."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check for geometry columns
        geom_col_row = await conn.fetchrow(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = $1 AND table_name = $2 AND data_type = 'USER-DEFINED'
            LIMIT 1
            """,
            schema, table
        )
        if not geom_col_row:
            return {"error": f"No geometry column found in {schema}.{table}"}
            
        geom_col = geom_col_row["column_name"]
        extent_row = await conn.fetchrow(
            f'SELECT ST_Extent("{geom_col}") as box FROM "{schema}"."{table}"'
        )
        # ST_Extent returns string like "BOX(xmin ymin, xmax ymax)"
        if not extent_row or not extent_row["box"]:
            return {"error": "Empty or null extent"}
            
        return {"table": table, "extent": extent_row["box"]}


@audit("DIO")
async def clip_to_bbox(
    table: str,
    west: float,
    south: float,
    east: float,
    north: float,
    geom_col: str = "geometry",
) -> Dict[str, Any]:
    """
    Spatially clip *table* to a bounding box and write the result to
    clean_data.<table>_clipped.  Returns row count of the clipped output.
    """
    dest = f"{table}_clipped"
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS clean_data."{dest}" AS
            SELECT * FROM public."{table}"
            WHERE ST_Intersects(
                "{geom_col}",
                ST_MakeEnvelope($1, $2, $3, $4, 4326)
            )
            LIMIT 0
            """
        )
        await conn.execute(f'TRUNCATE clean_data."{dest}"')
        result = await conn.execute(
            f"""
            INSERT INTO clean_data."{dest}"
            SELECT * FROM public."{table}"
            WHERE ST_Intersects(
                "{geom_col}",
                ST_MakeEnvelope($1, $2, $3, $4, 4326)
            )
            """,
            west, south, east, north,
        )
    rows_inserted = int(result.split()[-1])
    return {"destination": f"clean_data.{dest}", "rows_inserted": rows_inserted}


@audit("DIO")
async def clean_claims(
    missing_strategy: str = "drop",
    depth_unit: str = "inches",
) -> Dict[str, Any]:
    """
    Clean NFIP claims:
    - Handle nulls in key columns (strategy: 'drop' | 'mean')
    - Convert waterdepth to feet if depth_unit == 'inches'
    - Write result to clean_data.claims_processed
    """
    import pandas as pd

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM public.collier_claims LIMIT 100000")

    if not rows:
        return {"status": "error", "message": "collier_claims not found or empty"}

    df = pd.DataFrame([dict(r) for r in rows])
    key_cols = ["buildingdamageamount", "buildingpropertyvalue", "waterdepth",
                "lowestfloorelevation", "reportedzipcode"]

    if missing_strategy == "drop":
        df = df.dropna(subset=[c for c in key_cols if c in df.columns])
    else:
        for col in key_cols:
            if col in df.columns and df[col].dtype in ("float64", "int64"):
                df[col] = df[col].fillna(df[col].mean())

    if depth_unit == "inches" and "waterdepth" in df.columns:
        df["waterdepth"] = df["waterdepth"] / 12.0

    # Write to clean_data schema
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS clean_data.claims_processed")
        cols_ddl = ", ".join(
            f'"{c}" TEXT' for c in df.columns
        )
        await conn.execute(f"CREATE TABLE clean_data.claims_processed ({cols_ddl})")
        records = [tuple(str(v) if v is not None else None for v in row) for row in df.itertuples(index=False)]
        await conn.copy_records_to_table(
            "claims_processed",
            schema_name="clean_data",
            records=records,
            columns=list(df.columns),
        )

    return {
        "status": "ok",
        "destination": "clean_data.claims_processed",
        "rows_written": len(df),
        "columns": list(df.columns),
    }


@audit("DIO")
async def eda_summary(table: str, schema: str = "clean_data") -> Dict[str, Any]:
    """Return basic EDA stats (min, max, mean, null count) for numeric columns."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        cols_info = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            """,
            schema, table,
        )

    numeric_cols = [
        r["column_name"] for r in cols_info
        if "int" in r["data_type"] or "numeric" in r["data_type"] or "float" in r["data_type"] or "double" in r["data_type"]
    ]

    if not numeric_cols:
        return {"table": f"{schema}.{table}", "numeric_columns": [], "stats": {}}

    stats: Dict[str, Any] = {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        for col in numeric_cols[:20]:  # cap at 20 columns
            row = await conn.fetchrow(
                f"""
                SELECT
                    MIN("{col}"::NUMERIC)  AS min,
                    MAX("{col}"::NUMERIC)  AS max,
                    AVG("{col}"::NUMERIC)  AS mean,
                    COUNT(*) - COUNT("{col}") AS null_count
                FROM "{schema}"."{table}"
                """
            )
            stats[col] = {
                "min": float(row["min"]) if row["min"] is not None else None,
                "max": float(row["max"]) if row["max"] is not None else None,
                "mean": float(row["mean"]) if row["mean"] is not None else None,
                "null_count": int(row["null_count"]),
            }

    return {"table": f"{schema}.{table}", "numeric_columns": numeric_cols, "stats": stats}


@audit("DIO")
async def export_handoff(
    target_col: str = "buildingdamageamount",
    feature_cols: Optional[List[str]] = None,
    source_table: Optional[str] = None,
    source_schema: str = "clean_data",
) -> Dict[str, Any]:
    """
    Build and return a HandoffToken for MEL, listing available
    clean_data or public tables.
    """
    if feature_cols is None:
        feature_cols = [
            "buildingpropertyvalue", "lowestfloorelevation",
            "waterdepth", "reportedzipcode", "occupancytype",
            "ratedfloodzone", "causeofdamage",
        ]

    pool = await get_pool()
    
    if source_table:
        tables_rows = [{"table_name": source_table}]
    else:
        async with pool.acquire() as conn:
            tables_rows = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'clean_data'
                """
            )

    table_infos: List[TableInfo] = []
    async with pool.acquire() as conn:
        for tr in tables_rows:
            tname = tr["table_name"]
            cols = await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                """,
                source_schema, tname,
            )
            cnt = await conn.fetchval(f'SELECT COUNT(*) FROM "{source_schema}"."{tname}"')
            table_infos.append(
                TableInfo(
                    name=tname,
                    schema=source_schema,
                    row_count=int(cnt),
                    columns=[r["column_name"] for r in cols],
                )
            )

    token = HandoffToken(
        schema_name=source_schema,
        tables=table_infos,
        feature_cols=feature_cols,
        target_col=target_col,
    )
    return token.model_dump(mode="json")
