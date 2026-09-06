const leftPad = require("left-pad");
const express = require("express");

const app = express();
app.get("/reference/:id", (req, res) => res.send(leftPad(req.params.id, 12, "0")));

module.exports = app;
