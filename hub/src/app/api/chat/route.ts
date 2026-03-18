import { NextResponse } from "next/server";

// ── Study Config Parsing ────────────────────────────────────────────────────
const TRAINING_KEYWORDS = /training\s+data|train(?:ing)?\s+on|using\s+.+\s+as\s+training|claims|cleaned/i;
const PARCELS_KEYWORDS  = /parcel|apply\s+(?:that\s+)?model|target\s+(?:area|parcels|data)|inference/i;
const VALUES_KEYWORDS   = /value|property\s+value|assessed|real\s+value/i;
const TARGET_KEYWORDS   = /predict(?:ing)?\s+(\w+)|model\s+for\s+(\w+)/i;

function getSurroundingContext(text: string, target: string): string {
  const idx = text.toLowerCase().indexOf(target.toLowerCase());
  if (idx < 0) return text;
  return text.slice(Math.max(0, idx - 80), idx + 80);
}

function extractStudyConfig(message: string) {
  const extracted: Record<string, string | null> = {
    trainingTable: null,
    parcelsTable: null,
    valuesTable: null,
    targetColumn: null,
  };
  const tableMatches = [...message.matchAll(/([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)/gi)].map(m => m[1]);
  for (const table of tableMatches) {
    const ctx = getSurroundingContext(message, table);
    if (!extracted.trainingTable && TRAINING_KEYWORDS.test(ctx)) {
      extracted.trainingTable = table;
    } else if (!extracted.parcelsTable && PARCELS_KEYWORDS.test(ctx)) {
      extracted.parcelsTable = table;
    } else if (!extracted.valuesTable && VALUES_KEYWORDS.test(ctx)) {
      extracted.valuesTable = table;
    }
  }
  // Fallback: assign in order if context matching missed some
  if (tableMatches.length >= 1 && !extracted.trainingTable) extracted.trainingTable = tableMatches[0];
  if (tableMatches.length >= 2 && !extracted.parcelsTable)  extracted.parcelsTable  = tableMatches[1];
  if (tableMatches.length >= 3 && !extracted.valuesTable)   extracted.valuesTable   = tableMatches[2];

  const targetMatch = message.match(TARGET_KEYWORDS);
  if (targetMatch) extracted.targetColumn = targetMatch[1] || targetMatch[2] || null;

  return extracted;
}

function isStudyConfigMessage(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    (lower.includes("training") || lower.includes("train on") || lower.includes("claims")) &&
    (lower.includes("parcel") || lower.includes("apply") || lower.includes("model")) &&
    /[a-z_]+\.[a-z_]+/.test(lower)
  );
}

// ── Inference call helper ───────────────────────────────────────────────────
async function callInference(url: string, model: string, messages: any[]): Promise<string> {
  const response = await fetch(`${url}/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, messages, temperature: 0.7, max_tokens: 1024, stream: false }),
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text.slice(0, 120)}`);
  }
  const data = await response.json();
  const reply = data.choices?.[0]?.message?.content;
  if (!reply) throw new Error("Empty response from model");
  return reply;
}

// ── Route handler ───────────────────────────────────────────────────────────
export async function POST(request: Request) {
  try {
    const { message, history, agent, lmStudioIp } = await request.json();

    if (!message) {
      return NextResponse.json({ success: false, error: "Missing message" }, { status: 400 });
    }

    // Study config detection
    const studyConfig = isStudyConfigMessage(message) ? extractStudyConfig(message) : null;

    // Agent-aware system prompt
    const agentContext: Record<string, string> = {
      DIO:  "You are the DIO (Data Operator) agent for the SLR pipeline. Help discover, query, and visualize PostGIS geospatial tables including NFIP claims data.",
      MEL:  "You are the MEL (Model Evaluator) agent for the SLR pipeline. Help interpret XGBoost/GMM ensemble metrics — R², RMSE, MAE — and feature importance.",
      SIMO: "You are the SIMO (Impact Modeler) agent for the SLR pipeline. Help interpret parcel-level flood damage simulations and sea level rise scenarios.",
    };
    const basePrompt = agent
      ? agentContext[agent]
      : "You are the SLR Pipeline orchestrator. Coordinate DIO (data), MEL (modeling), and SIMO (simulation) agents for sea level rise flood damage assessment.";

    const studyAddendum = studyConfig
      ? `\n\nStudy config detected: training=${studyConfig.trainingTable}, parcels=${studyConfig.parcelsTable}, values=${studyConfig.valuesTable}. Briefly acknowledge and confirm the pipeline is configured.`
      : "";

    const messages = [
      { role: "system", content: basePrompt + studyAddendum },
      ...((history ?? []).slice(-10).map((m: any) => ({
        role: m.role === "system" ? "assistant" : m.role,
        content: m.content,
      }))),
      { role: "user", content: message },
    ];

    // ── Priority fallback: configured URL → VM Ollama → local Ollama ──────────
    // Server-side env var takes precedence; client-sent lmStudioIp is a secondary override
    const ENV_URL   = process.env.NEXT_PUBLIC_LM_STUDIO_URL ?? "";
    const ENV_MODEL = process.env.NEXT_PUBLIC_LM_STUDIO_MODEL ?? "mistral:7b-instruct";
    const primaryUrl = lmStudioIp ?? ENV_URL ?? "http://localhost:1234/v1";

    // Build ordered candidate list — VM env URL first, then user-configured, then local Ollama
    const OLLAMA_LOCAL  = "http://localhost:11434/v1";
    const OLLAMA_MODELS = ["mistral:7b-instruct", "phi3:mini", "mistral", "llama3"];

    const candidates: { url: string; model: string }[] = [];

    // 1. VM endpoint from .env.local (highest priority)
    if (ENV_URL) candidates.push({ url: ENV_URL, model: ENV_MODEL });

    // 2. User-configured URL from Prepper (if different from env)
    if (primaryUrl && primaryUrl !== ENV_URL) {
      candidates.push({ url: primaryUrl, model: ENV_MODEL });
      candidates.push({ url: primaryUrl, model: "local-model" });
    }

    // 3. Local Ollama fallback
    OLLAMA_MODELS.forEach(m => candidates.push({ url: OLLAMA_LOCAL, model: m }));

    for (const { url, model } of candidates) {
      try {
        const reply = await callInference(url, model, messages);
        return NextResponse.json({
          success: true,
          reply,
          studyConfig,
          backend: `${url} — ${model}`,
        });
      } catch {
        // Try next candidate
        continue;
      }
    }

    return NextResponse.json({
      success: false,
      error: `No inference server reachable. Start LM Studio at ${primaryUrl}, or run: ollama serve && ollama pull mistral`,
    }, { status: 503 });

  } catch (error: any) {
    console.error("Chat API Error:", error);
    return NextResponse.json({ success: false, error: error.message ?? "Internal server error" }, { status: 500 });
  }
}
