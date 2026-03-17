import { NextResponse } from "next/server";
import { Client } from "pg";

export async function POST(request: Request) {
  try {
    const { host, port, user, password, database, table } = await request.json();

    if (!table) {
      return NextResponse.json({ success: false, error: "Table name is required" }, { status: 400 });
    }

    const client = new Client({
      host,
      port: parseInt(port) || 5432,
      user,
      password,
      database,
      ssl: host.includes("azure.com") ? { rejectUnauthorized: false } : false,
      connectionTimeoutMillis: 10000,
    });

    try {
      await client.connect();
      
      // Find the geometry column name first
      const colQuery = `
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = $1 
          AND (udt_name = 'geometry' OR udt_name = 'geography')
        LIMIT 1
      `;
      const colRes = await client.query(colQuery, [table.split('.').pop()]);
      
      if (colRes.rows.length === 0) {
        await client.end();
        return NextResponse.json({ success: false, error: "No geometry column found" }, { status: 404 });
      }

      const geomCol = colRes.rows[0].column_name;

      // Extract as GeoJSON, limiting to 1000 for performance
      // We use ST_Transform to 4326 (WGS84) which Leaflet expects
      const query = `
        SELECT jsonb_build_object(
          'type', 'FeatureCollection',
          'features', jsonb_agg(features.feature)
        )
        FROM (
          SELECT jsonb_build_object(
            'type', 'Feature',
            'id', __id,
            'geometry', ST_AsGeoJSON(ST_Transform(${geomCol}, 4326))::jsonb,
            'properties', to_jsonb(inputs) - '${geomCol}' - '__id'
          ) AS feature
          FROM (
            SELECT *, row_number() OVER () as __id 
            FROM ${table} 
            LIMIT 1000
          ) inputs
        ) features;
      `;
      
      const result = await client.query(query);
      await client.end();
      
      return NextResponse.json({ 
        success: true, 
        data: result.rows[0].jsonb_build_object || { type: 'FeatureCollection', features: [] }
      });
    } catch (dbError: any) {
      console.error("GeoJSON Fetch Error:", dbError);
      return NextResponse.json(
        { success: false, error: dbError.message || "Database query failed" },
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
