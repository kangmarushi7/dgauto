const fs = require("fs");
const path = require("path");
const config = require("../config");

function loadAliases() {
  try {
    if (!fs.existsSync(config.aliasesPath)) {
      return { aliases: {}, canonical: {} };
    }
    return JSON.parse(fs.readFileSync(config.aliasesPath, "utf8"));
  } catch {
    return { aliases: {}, canonical: {} };
  }
}

function saveAliases(data) {
  const dir = path.dirname(config.aliasesPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(config.aliasesPath, JSON.stringify(data, null, 2), "utf8");
}

function normalizeKey(name) {
  return String(name || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[.'']/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/**
 * Resolve a scraped display name to a canonical player name.
 * Maintains a simple alias table for mismatches across sources.
 */
function resolvePlayerName(rawName, { addAlias = false, canonicalHint = null } = {}) {
  const data = loadAliases();
  const key = normalizeKey(rawName);
  if (!key) return null;

  if (data.aliases[key]) return data.aliases[key];
  if (data.canonical[key]) return data.canonical[key];

  const canonical = canonicalHint || String(rawName).trim();
  if (addAlias) {
    data.aliases[key] = canonical;
    data.canonical[normalizeKey(canonical)] = canonical;
    saveAliases(data);
  }
  return canonical;
}

function addAlias(alias, canonical) {
  const data = loadAliases();
  data.aliases[normalizeKey(alias)] = canonical;
  data.canonical[normalizeKey(canonical)] = canonical;
  saveAliases(data);
}

function slugifyPlayerId(sport, name, team = "") {
  const base = normalizeKey(name).replace(/\s+/g, "-");
  const teamPart = normalizeKey(team).replace(/\s+/g, "-");
  return `${sport}:${base}${teamPart ? `:${teamPart}` : ""}`;
}

module.exports = {
  loadAliases,
  saveAliases,
  normalizeKey,
  resolvePlayerName,
  addAlias,
  slugifyPlayerId,
};
