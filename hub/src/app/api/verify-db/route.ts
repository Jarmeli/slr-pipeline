import { NextResponse } from "next/server";
import { Client } from "pg";

export async function POST(request: Request) {
  try {
    const { host, port, user, password, database, connectionString } = await request.json();

    let clientConfig: any = {};
    if (connectionString) {
      clientConfig.connectionString = connectionString;
    } else {
      clientConfig = {
        host,
        port: parseInt(port) || 5432,
        user,
        password,
        database,
      };
    }

    // Add SSL for Azure
    if (connectionString?.includes("azure.com") || host?.includes("azure.com")) {
      clientConfig.ssl = { rejectUnauthorized: false };
    }

    clientConfig.connectionTimeoutMillis = 5000;

    const client = new Client(clientConfig);

    try {
      await client.connect();
      await client.query("SELECT 1");
      await client.end();
      return NextResponse.json({ success: true, message: "Connected successfully" });
    } catch (dbError: any) {
      console.error("DB Connection Error:", dbError);
      return NextResponse.json(
        { success: false, error: dbError.message || "Could not connect to database" },
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
