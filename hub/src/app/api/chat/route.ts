import { NextResponse } from "next/server";

// Regex patterns to extract table references from natural language
const TABLE_PATTERN = /(?:schema[._\s])?([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*|[a-z_][a-z0-9_]{3,})/gi;
const TRAINING_KEYWORDS = /training\s+data|train(?:ing)?\s+on|using\s+.+\s+as\s+training|claims|cleaned/i;
const PARCELS_KEYWORDS = /parcel|apply\s+(?:that\s+)?model|target\s+(?:area|parcels|data)|inference/i;
const VALUES_KEYWORDS = /value|property\s+value|assessed|real\s+value/i;
const TARGET_KEYWORDS = /predict(?:ing)?\s+(\w+)|model\s+for\s+(\w+)/i;

function extractStudyConfig(message: string) {
  const extracted: Record<string, string | null> = {
    trainingTable: null,
    parcelsTable: null,
    valuesTable: null,
    targetColumn: null,
  };

  // Extract all schema.table references
  const tableMatches = [...message.matchAll(/([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)/gi)].map(m => m[1]);

  for (const table of tableMatches) {
    const surroundingCtx = getSurroundingContext(message, table);
    if (!extracted.trainingTable && TRAINING_KEYWORDS.test(surroundingCtx)) {
      extracted.trainingTable = table;
    } else if (!extracted.parcelsTable && PARCELS_KEYWORDS.test(surroundingCtx)) {
      extracted.parcelsTable = table;
    } else if (!extracted.valuesTable && VALUES_KEYWORDS.test(surroundingCtx)) {
      extracted.valuesTable = table;
    }
  }

  // If not all resolved by context, assign in order
  if (tableMatches.length >= 1 && !extracted.trainingTable) extracted.trainingTable = tableMatches[0];
  if (tableMatches.length >= 2 && !extracted.parcelsTable) extracted.parcelsTable = tableMatches[1];
  if (tableMatches.length >= 3 && !extracted.valuesTable) extracted.valuesTable = tableMatches[2];

  // Extract target column
  const targetMatch = message.match(TARGET_KEYWORDS);
  if (targetMatch) extracted.targetColumn = targetMatch[1] || targetMatch[2] || null;

  return extracted;
}

function getSurroundingContext(text: string, target: string): string {
  const idx = text.toLowerCase().indexOf(target.toLowerCase());
  if (idx < 0) return text;
  return text.slice(Math.max(0, idx - 80), idx + 80);
}

function isStudyConfigMessage(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    (lower.includes("training") || lower.includes("train on") || lower.includes("claims")) &&
    (lower.includes("parcel") || lower.includes("apply") || lower.includes("model")) &&
    /[a-z_]+\.[a-z_]+/.test(lower)
  );
}

export async function POST(request: Request) {
  try {
    const { message, history, agent, lmStudioIp } = await request.json();

    if (!message || !lmStudioIp) {
      return NextResponse.json({ success: false, error: "Missing message or LM Studio endpoint" }, { status: 400 });
    }

    // ── Study Config Detection ──────────────────────────────────────────────
    const isConfig = isStudyConfigMessage(message);
    const studyConfig = isConfig ? extractStudyConfig(message) : null;

    // ── Agent-Aware System Prompt ───────────────────────────────────────────
    const agentContext: Record<string, string> = {
      DIO: "You are the DIO (Data Operator) assistant for the SLR pipeline. Help the user discover, query, and visualize PostGIS geospatial data tables. You understand spatial data, geometry types, and NFIP claims.",
      MEL: "You are the MEL (Model Evaluator) assistant for the SLR pipeline. Help the user understand model training results, R-squared scores, RMSE values, and feature importance from the XGBoost/GMM ensemble.",
      SIMO: "You are the SIMO (Impact Modeler) assistant for the SLR pipeline. Help the user interpret sea level rise simulation results, parcel damage estimates, and flood inundation scenarios.",
    };

    const basePrompt = agent
      ? agentContext[agent]
      : "You are the SLR Pipeline orchestrator assistant. Help coordinate analysis across DIO (data), MEL (modeling), and SIMO (simulation) agents for sea level rise flood damage assessments.";

    const studyPromptAddendum = studyConfig
      ? `\n\nThe user has specified a study configuration. Extracted: training_table=${studyConfig.trainingTable}, parcels_table=${studyConfig.parcelsTable}, values_table=${studyConfig.valuesTable}. Acknowledge these settings and confirm the pipeline is ready to proceed. Be concise.`
      : "";

    const systemPrompt = basePrompt + studyPromptAddendum;

    const messages = [
      { role: "system", content: systemPrompt },
      ...((history || []).slice(-10).map((m: any) => ({
        role: m.role === "system" ? "assistant" : m.role,
        content: m.content,
      }))),
      { role: "user", content: message },
    ];

    // ── Call LM Studio ──────────────────────────────────────────────────────
    const response = await fetch(`${lmStudioIp}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "local-model",
        messages,
        temperature: 0.7,
        max_tokens: 1024,
        stream: false,
      }),
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      const errText = await response.text();
      return NextResponse.json({ success: false, error: `LM Studio error: ${response.status} - ${errText}` }, { status: 502 });
    }

    const data = await response.json();
    const reply = data.choices?.[0]?.message?.content || "No response from model.";

    return NextResponse.json({ success: true, reply, studyConfig });
  } catch (error: any) {
    console.error("Chat API Error:", error);
    if (error.name === "TimeoutError") {
      return NextResponse.json({ success: false, error: "LM Studio request timed out. Is it running?" }, { status: 504 });
    }
    return NextResponse.json({ success: false, error: error.message || "Internal server error" }, { status: 500 });
  }
}
