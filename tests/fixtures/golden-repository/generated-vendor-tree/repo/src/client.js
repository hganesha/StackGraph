const axios = require("axios");

exports.fetchCatalog = () => axios.get("https://catalog.internal/items");
