const express = require("express");

const app = express();
app.get("/ledger", (req, res) => res.json({ ok: true }));

module.exports = app;
