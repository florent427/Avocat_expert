// Génère lib/contracts.generated.ts depuis les schémas JSON des contrats
// (packages/contracts/schemas, eux-mêmes exportés des modèles Pydantic).
// Usage : npm run contracts        (écrit le fichier)
//         npm run contracts:check  (échoue si le fichier n'est pas à jour)
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { compile } from "json-schema-to-typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const schemas = path.resolve(here, "../../../packages/contracts/schemas");
const target = path.resolve(here, "../lib/contracts.generated.ts");
const names = ["SourcedAnswer", "AnswerRequest", "CitationVerification"];

// Un schéma unique regroupe les définitions de tous les contrats : chaque type
// partagé (SourceReference…) n'est déclaré qu'une fois, sans ambiguïté de nom.
// Les titres des propriétés sont retirés pour éviter un alias par champ.
function stripTitles(node, keep) {
  if (Array.isArray(node)) return node.map((n) => stripTitles(n, false));
  if (node && typeof node === "object") {
    const out = {};
    for (const [key, value] of Object.entries(node)) {
      if (key === "title" && !keep) continue;
      if (key === "$defs") {
        out.$defs = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, stripTitles(v, true)]));
      } else {
        out[key] = stripTitles(value, false);
      }
    }
    return out;
  }
  return node;
}

const defs = {};
for (const name of names) {
  const schema = JSON.parse(await readFile(path.join(schemas, `${name}.schema.json`), "utf8"));
  for (const [k, v] of Object.entries(schema.$defs ?? {})) {
    if (defs[k] && JSON.stringify(defs[k]) !== JSON.stringify(v)) {
      throw new Error(`définition ${k} divergente entre contrats`);
    }
    defs[k] = v;
  }
  const root = { ...schema };
  delete root.$defs;
  defs[name] = root;
}
const combined = stripTitles(
  {
    title: "AvocatExpertContracts",
    type: "object",
    additionalProperties: false,
    properties: Object.fromEntries(names.map((n) => [n, { $ref: `#/$defs/${n}` }])),
    $defs: defs,
  },
  true,
);
const body = await compile(combined, "AvocatExpertContracts", {
  bannerComment: "",
  additionalProperties: false,
  unreachableDefinitions: true,
  style: { semi: true, singleQuote: false },
});
const output =
  "// Fichier généré par scripts/gen-contracts.mjs — ne pas modifier à la main.\n" +
  "// Source : packages/contracts/schemas/*.schema.json (modèles Pydantic).\n\n" +
  body;

if (process.argv.includes("--check")) {
  const current = await readFile(target, "utf8").catch(() => "");
  if (current !== output) {
    console.error("lib/contracts.generated.ts n'est pas à jour : lancer `npm run contracts`.");
    process.exit(1);
  }
} else {
  await writeFile(target, output);
  console.log(`écrit : ${path.relative(process.cwd(), target)}`);
}
