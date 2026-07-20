#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });

const db = require("../db/client");

db.initSchema();
console.log("Database initialized at", require("../config").dbPath);
db.close();
