# Domain Adaptation

Use this guide to adapt the skill to fields beyond AI.

## 1. Start With the Right Entity Types

Not every domain needs the same entity groups.

Examples:

### Research-heavy domain
- `person`
- `institution`
- `lab`
- `project`

### Consumer market domain
- `company`
- `brand`
- `product`
- `creator`

### Infrastructure domain
- `company`
- `product`
- `open-source project`
- `standards body`

## 2. Change the Source Mix

Different fields generate updates in different places.

Examples:

### Developer tools
- docs
- changelog
- GitHub releases
- engineering blog

### Policy or regulation
- agency websites
- official statements
- public dockets
- hearings

### Consumer tech
- product blogs
- launch pages
- keynote videos
- app store release notes

## 3. Change the Ranking Logic

The same scoring categories do not always fit.

Choose criteria that match the field:
- product shipping
- research output
- regulatory influence
- market share
- ecosystem leverage
- community adoption

## 4. Keep the Storage Model Stable

Try not to redesign the whole database for each new topic.

Usually you can keep:
- `entities`
- `entity_sources`
- `entity_updates`
- `collection_runs`

and only change:
- domain labels
- entity groups
- source-type mix
- update filters

## 5. Make Scope Explicit

Before collecting, pin these down:
- domain name
- geography
- language
- entity groups
- ranking criteria
- update window
- allowed source types

This prevents the tracker from drifting.
