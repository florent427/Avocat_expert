// API simulée pour les tests de bout en bout : renvoie une réponse réelle
// enregistrée (fixtures/) et mémorise les en-têtes reçus, pour vérifier que
// le jeton est ajouté côté serveur.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const answer = readFileSync(new URL("./fixtures/answer-L5411-1.json", import.meta.url), "utf8");
let last = null;

createServer((req, res) => {
  if (req.url === "/__last") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(last));
    return;
  }
  let body = "";
  req.on("data", (chunk) => (body += chunk));
  req.on("end", () => {
    if (req.method === "POST" && req.url === "/v1/answer") {
      last = { authorization: req.headers.authorization ?? null, body: JSON.parse(body || "{}") };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(answer);
      return;
    }
    res.writeHead(404).end();
  });
}).listen(Number(process.env.MOCK_API_PORT ?? 8099), "127.0.0.1");
