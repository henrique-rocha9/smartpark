import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type,x-device-key",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), {
    status: s,
    headers: { ...cors, "Content-Type": "application/json" },
  });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const url = new URL(req.url);

  // POST: o ESP32 envia as leituras (protegido por x-device-key)
  if (req.method === "POST") {
    if (req.headers.get("x-device-key") !== Deno.env.get("DEVICE_KEY")) {
      return json({ error: "unauthorized" }, 401);
    }
    const b = await req.json();
    const rows = b.vagas.map((v: any) => ({
      dispositivo: b.dispositivo,
      grandeza: "distancia",
      vaga: v.vaga,
      status: v.status,
      valor: v.distancia_cm,
      unidade: "cm",
    }));
    const { error } = await db.from("leituras").insert(rows);
    return error ? json({ error: error.message }, 500) : json({ ok: true });
  }

  // GET ?r=latest  -> ultima leitura de cada vaga
  // GET ?r=history -> historico (limit opcional, max 300)
  const r = url.searchParams.get("r") || "latest";
  const limit = Math.min(Number(url.searchParams.get("limit") || 60), 300);
  const { data, error } = await db.from("leituras").select("*")
    .order("criado_em", { ascending: false })
    .limit(r === "latest" ? 30 : limit);
  if (error) return json({ error: error.message }, 500);

  if (r === "latest") {
    const m: Record<number, any> = {};
    for (const x of data!) if (!m[x.vaga]) m[x.vaga] = x;
    return json({ server_time: new Date().toISOString(), vagas: Object.values(m) });
  }
  return json({ server_time: new Date().toISOString(), historico: data });
});
