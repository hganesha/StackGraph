const express = require("express");
const { Pool } = require("pg");

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const app = express();

app.get("/invoices/:id", async (req, res) => {
  const result = await pool.query("SELECT * FROM invoice WHERE id = $1", [req.params.id]);
  res.json(result.rows[0] ?? null);
});

module.exports = app;
