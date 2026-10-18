# Synthetic sample data

Everything here is **synthetic**: invented names, `example.com` addresses and made-up phone numbers. No real client or personal data.

- `source.csv`: 30 CRM contacts/deals (the trusted original).
- `destination.csv`: the "migrated" copy, 31 rows, with problems deliberately injected.
- `config.json`: validation rules used for the sample run.
- `known_errors.json`: the hand-written answer key (28 expected issues). `tests/test_example_dataset.py` asserts the validator reports exactly these.

## Intentionally introduced errors and the expected outcome

| Category you asked for | Record(s) | What was changed | Expected result |
|---|---|---|---|
| Missing contact | C005, C011, C019 | Rows deleted from the destination | `missing_record` (error) |
| Duplicate identifier | C007 | Row repeated, identical | `duplicate_id` (error), "all occurrences are identical" |
| Duplicate identifier | C014 | Row repeated with a different email | `duplicate_id` (error), "conflicting values", plus `value_mismatch` on `email` |
| Invalid email address | C023 | `tolu.kalu@example.com` became `tolu.kalu@example` | `rule_email_format` plus `value_mismatch` |
| Missing required field | C020 | Email blanked | `missing_value` plus `rule_required_field` |
| Changed field value | C002 | Email domain `.com` to `.org` | `value_mismatch` |
| Changed field value | C009 | `4500.00` became `450.00` | `value_mismatch` |
| Changed field value | C030 | `opportunity` became `lead` | `value_mismatch` |
| Changed field value | C018 | `7160.00` became `TBD` | `value_mismatch`, `rule_not_numeric` |
| Changed field value | C027 | `250.00` became `-250.00` | `value_mismatch`, `rule_numeric_range` |
| Harmless formatting difference | C003 | Email case only | `formatting_difference` (info), normalization `casefold` |
| Harmless formatting difference | C016 | `+2348035550016` became `+234 803 555 0016` | `formatting_difference` (info), normalization `phone_digits` |
| Harmless formatting difference | C025 | `2024-03-15` became `03/15/2024` | `formatting_difference` (info) plus `rule_date_format` |
| Whitespace inconsistency | C012 | Trailing space in `last_name` | `whitespace_difference` (warning) |
| Unexpected destination record | C031 | New row not in source | `unexpected_record` (warning) |
| Unexpected destination record | C032 | Copy of C008 under a new id | `unexpected_record` plus `duplicate_record` (warning) |
| Schema | `company` | Column dropped | `missing_column` (error) |
| Schema | `import_batch` | Column added | `unexpected_column` (warning) |
| Schema | `deal_amount` | Text value makes numeric column a string | `type_mismatch` (error) |

A single injected problem can raise more than one issue on purpose (for example a blanked email is both a `missing_value` comparison result and a `rule_required_field` rule violation).
