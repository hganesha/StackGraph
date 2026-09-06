const express = require("express");
const Stripe = require("stripe");

const stripe = new Stripe(process.env.STRIPE_KEY);
const app = express();

app.post("/payments", async (req, res) => {
  const intent = await stripe.paymentIntents.create(req.body);
  res.json(intent);
});

module.exports = app;
