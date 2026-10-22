# Edit rules outside Local Bookkeeper

## Download, edit, upload

1. In **Reports**, choose **Download rules file**. This downloads rules and
   category definitions for the entire active profile, regardless of page filters.
2. Open the JSON file in a text editor, or give it to an AI to edit. It is
   formatted with indentation and includes a `_help` guide at the top.
3. Edit existing entries in `rules`, or copy an entry to add a rule. Keep an
   existing rule's `key` and `type` unchanged. Give each new rule a unique key,
   such as `lowes-supplies`. Do not put comments inside JSON.
4. In **Rules & automation** or **Data & storage**, choose **Upload edited rules
   file**. Select **Update rules with matching keys and add new rules** and check
   the business/account mappings. Choose **Preview import**.
5. Inspect current and proposed settings, new rules, unchanged entries and skips.
   Choose **Apply to whole profile** to save. Each rule still applies only within
   its specified business/account/amount conditions.
6. The optional rule check opens a second preview across all businesses and
   years. Apply it to update eligible unreviewed transactions. Already-reviewed
   transactions retain their decisions.

The file is a portable configuration, not a live connection: saving edits to it
does not affect the app until you upload and apply its preview.

## Rule fields

| Field | Meaning |
| --- | --- |
| `key` | Identity of the rule. Keep it when editing; use a new unique value when adding. |
| `type` | `expense` for money out; `credit` for money in. To change type, create a new rule and pause the old one. |
| `patterns` | An array of alternative merchant text fragments. `Lowes` matches `Lowes123` and `Lowes234`. Any one may match, ignoring case and punctuation. Each fragment is 2–120 normalized characters. |
| `sourceCategories` | Optional array of original statement category labels. Matches complete normalized labels. Use an empty array for no restriction. |
| `businessKey` | The destination business key from `businesses`. Required for expenses and business refunds. |
| `accountKey` | A source account key from `accounts`, or `null` to cover all source accounts in the profile. |
| `category` | The bookkeeping category name to assign. It must exist in the destination or be included in `categories`. |
| `minCents` / `maxCents` | Optional nonnegative whole-number USD cents: `2500` means $25.00. `null` means no limit. |
| `mode` | `suggest`, `categorize` (assign and review later), or `review` (trusted automatic review). |
| `includeInTotals` | `true` includes eligible expenses/refunds in totals; requires `mode: "review"`. Otherwise `false`. |
| `active` | `true` enables the rule; `false` pauses it. |
| `treatment` | Empty string for expense rules. Credit rules use `payment`, `refund`, `statement_credit`, or `excluded_credit`. |

All conditions must match together, apart from alternatives inside `patterns` or
`sourceCategories`. A category-only rule has `patterns: []` and one or more source
category labels. Up to 200 text fragments and 200 source category labels are
supported per rule. Merchant rules retain priority over category-only rules.

`accountName` and `businessName` alongside exported rules are display labels.
Changing those labels does not change scope: change the corresponding key or
the upload mapping. Keep referenced keys in the file's businesses/accounts lists.

## Applying automation settings

By default, existing rules keep their current automation/inclusion settings, and
new rules start as **Suggest only**. To apply edits to `mode` or
`includeInTotals`, check **Keep the file’s automation and expense-inclusion
settings** before previewing. The preview lists trusted automatic review and
totals-inclusion settings. `active` always follows the file for imported updates.

Removing a rule from the file does not delete it from the profile. To pause it,
keep its entry/key and set `active` to `false`. Unrelated rules remain in place.
Rules whose keys match existing rules can change their conditions or destination.
An edit colliding with another enabled rule's matching conditions is skipped with
an explanation. **Add only** keeps existing rules unchanged.

Existing category definitions remain unchanged. To introduce another category,
add a category object with a unique `key` and the new name, then reference that
name from the rule. Renaming a category in the file adds the new definition;
it does not rename categories on existing transactions. Category entries specify
`businessKey` (or `null` for shared), `name`, `taxGroup`, `requiresReview` and
`active`.

## Complete example: a new merchant rule

For normal use, edit an actual export so its keys already match your profile.
This complete example creates a Supplies category and a Lowes rule after you map
the example business and account to your actual profile. Check the automation
settings option if you want its `categorize` mode to apply.

```json
{
  "format": "local-bookkeeper-rules-and-categories",
  "version": 1,
  "businesses": [
    { "key": "my-business", "name": "My business" }
  ],
  "accounts": [
    { "key": "my-card", "name": "Business card" }
  ],
  "categories": [
    {
      "key": "supplies-category",
      "businessKey": "my-business",
      "name": "Supplies",
      "taxGroup": "",
      "requiresReview": false,
      "active": true
    }
  ],
  "rules": [
    {
      "key": "lowes-supplies",
      "type": "expense",
      "patterns": ["Lowes"],
      "sourceCategories": [],
      "accountKey": "my-card",
      "businessKey": "my-business",
      "category": "Supplies",
      "treatment": "",
      "mode": "categorize",
      "includeInTotals": false,
      "active": true,
      "minCents": null,
      "maxCents": null
    }
  ]
}
```

Imports support version 1 JSON, up to 5 MB and 5,000 entries per collection.
Changed mappings, files or destination configuration require a new preview.
Configuration imports do not have batch Undo. Export the current rules again
after applying edits to keep your external copy in step with the app.
