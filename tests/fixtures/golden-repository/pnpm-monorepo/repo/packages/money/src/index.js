const { dinero } = require("dinero.js");

exports.minor = (amount, currency) => dinero({ amount, currency });
