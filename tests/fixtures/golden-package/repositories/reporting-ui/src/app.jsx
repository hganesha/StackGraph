import React from "react";
import leftPad from "left-pad";

export default function Reference({ id }) {
  return React.createElement("span", null, leftPad(String(id), 12, "0"));
}
