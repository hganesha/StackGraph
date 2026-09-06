const { of } = require("rxjs");

exports.stream = () => of(1, 2, 3);
