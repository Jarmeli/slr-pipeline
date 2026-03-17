import { NextResponse } from "next/server";
import { Client } from "pg";

export async function POST(request: Request) {
  try {
    const { host, port, user, password, database } = await request.json();

    const client = new Client({
      host,
      port: parseInt(port) || 5432,
      user,
      password,
      database,
      ssl: host.includes("azure.com") ? { rejectUnauthorized: false } : false,
      connectionTimeoutMillis: 5000,
    });

    try {
      await client.connect();
      
      // More robust query to find geospatial tables
      const query = `
        SELECT 
          n.nspname as schema, 
          c.relname as name, 
          a.attname as column,
          t.typname as type,
          postgis_typmod_srid(a.atttypmod) as srid
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE t.typname IN ('geometry', 'geography')
          AND n.nspname NOT IN ('information_schema', 'pg_catalog')
          AND c.relkind IN ('r', 'v', 'm') -- tables, views, materialized views
      `;
      
      const result = await client.query(query);
      await client.end();
      
      return NextResponse.json({ 
        success: true, 
        layers: result.rows.map(row => ({
          id: `${row.schema}.${row.name}`,
          name: row.name,
          schema: row.schema,
          type: row.type,
          srid: row.srid
        }))
      });
    } catch (dbError: any) {
      console.error("DB Layer Fetch Error:", dbError);
      return NextResponse.json(
        { success: false, error: dbError.message || "Could not fetch layers" },
        { status: 500 }
      );
    }
  } catch (error: any) {
    console.error("API Error:", error);
    return NextResponse.json(
      { success: false, error: "Internal server error" },
      { status: 500 }
    );
  }
}
