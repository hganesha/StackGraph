const leftPad = require("left-pad");

exports.reference = (id) => leftPad(String(id), 12, "0");
