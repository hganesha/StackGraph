// Minimal JSON Schema validator for the subset the OpenAPI document uses.
//
// Deliberately hand-rolled rather than pulling in a validator: it needs to cover
// exactly `type`, `required`, `additionalProperties`, `enum`, `$ref`, `anyOf`/`allOf`,
// and the string/array bounds the contract actually constrains — and those bounds are
// the point. A fixture that satisfies the shape but violates `minItems` still 422s
// against the real API, which is precisely the bug this file exists to catch.

const typeOf = (value) =>
  value === null ? "null" : Array.isArray(value) ? "array" : typeof value;

export function validate(schema, value, root, path = "$", errors = []) {
  if (!schema) return errors;

  if (schema.$ref) {
    const name = schema.$ref.split("/").at(-1);
    return validate(root.components.schemas[name], value, root, path, errors);
  }

  if (schema.anyOf || schema.oneOf) {
    const branches = schema.anyOf ?? schema.oneOf;
    const ok = branches.some((branch) => validate(branch, value, root, path, []).length === 0);
    if (!ok) errors.push(`${path}: matches none of the permitted variants`);
    return errors;
  }
  if (schema.allOf) {
    for (const branch of schema.allOf) validate(branch, value, root, path, errors);
    return errors;
  }

  if (schema.const !== undefined && value !== schema.const) {
    errors.push(`${path}: expected ${JSON.stringify(schema.const)}`);
  }
  if (schema.enum && !schema.enum.includes(value)) {
    errors.push(`${path}: ${JSON.stringify(value)} is not one of ${schema.enum.join(" | ")}`);
  }

  const actual = typeOf(value);
  if (schema.type && schema.type !== actual) {
    // JSON has one number type; the contract distinguishes integer.
    const numeric = schema.type === "integer" && actual === "number";
    if (!numeric) {
      errors.push(`${path}: expected ${schema.type}, got ${actual}`);
      return errors;
    }
  }

  if (actual === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${path}: shorter than minLength ${schema.minLength}`);
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push(`${path}: longer than maxLength ${schema.maxLength}`);
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      errors.push(`${path}: does not match ${schema.pattern}`);
    }
  }

  if (actual === "array") {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${path}: has ${value.length} items, minItems is ${schema.minItems}`);
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path}: has ${value.length} items, maxItems is ${schema.maxItems}`);
    }
    if (schema.items) {
      value.forEach((entry, index) => validate(schema.items, entry, root, `${path}[${index}]`, errors));
    }
  }

  if (actual === "object") {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}.${key}: required but absent`);
    }
    const properties = schema.properties ?? {};
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in properties)) errors.push(`${path}.${key}: not permitted by the contract`);
      }
    }
    for (const [key, entry] of Object.entries(value)) {
      // An explicit null against an optional field is how the wire says "absent".
      if (properties[key] && entry !== null) {
        validate(properties[key], entry, root, `${path}.${key}`, errors);
      }
    }
  }

  return errors;
}
