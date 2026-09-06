const Fastify = require("fastify");

const app = Fastify();
app.get("/shipments/:id", async (request) => ({ id: request.params.id }));

module.exports = app;
