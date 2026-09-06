const Anthropic = require("@anthropic-ai/sdk");
const express = require("express");

const client = new Anthropic();
const app = express();

app.post("/triage", async (req, res) => {
  const reply = await client.messages.create({
    model: "claude-sonnet-4-5",
    max_tokens: 512,
    messages: [{ role: "user", content: req.body.ticket }],
  });
  res.json(reply);
});

module.exports = app;
