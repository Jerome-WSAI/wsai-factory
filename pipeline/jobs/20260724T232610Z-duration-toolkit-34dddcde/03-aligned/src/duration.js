const ms = require("ms");

const SOFTWARE_NAME = "duration-toolkit";
const SOFTWARE_PURPOSE =
  "convert human duration labels to milliseconds for scheduling software";

function convertDurationToMilliseconds(label) {
  if (typeof label !== "string" || label.trim() === "") {
    throw new Error("duration label must be a non-empty string");
  }
  return ms(label);
}

function describeSoftware() {
  return {
    name: SOFTWARE_NAME,
    purpose: SOFTWARE_PURPOSE,
  };
}

module.exports = {
  SOFTWARE_NAME,
  SOFTWARE_PURPOSE,
  convertDurationToMilliseconds,
  describeSoftware,
};
