# Contributing

CoreFrame is licensed **GPL-3.0-or-later** (see `LICENSE.md`).

## Before you open a pull request

Every contribution needs a CLA. The reason is not bureaucracy: the project is
owned by one person, which is what makes it possible to relicense, dual-license
or sell it as a whole later. One merged pull request without a CLA breaks that
permanently, and it cannot be undone afterwards.

## Contributor License Agreement

By submitting a pull request you agree that:

1. You are the author of the contribution, or you have the right to submit it,
   and you have the legal right to grant this license.
2. You grant RoftCore a perpetual, worldwide, non-exclusive, royalty-free,
   irrevocable copyright license to reproduce, prepare derivative works of,
   publicly display, publicly perform, sublicense and distribute your
   contribution and such derivative works.
3. You grant RoftCore a perpetual, worldwide, non-exclusive, royalty-free,
   irrevocable patent license to make, have made, use, offer to sell, sell,
   import and otherwise transfer the contribution, where that license applies
   only to patent claims licensable by you that are necessarily infringed by
   your contribution.
4. **You keep your copyright.** This is a license grant, not an assignment, so
   you can keep using your own code for anything else.
5. The contribution is provided "as is", without warranty of any kind.

State `I have read the CLA and I agree` in the pull request description. Without
that line the PR is not merged.

## Practical rules

- Target the `development` branch. `main` only receives tested, released code.
- Read `AGENTS.md` before touching the UI or the process model: it lists the
  invariants and the pitfalls that have already cost real debugging time.
- Run `python tools/sync_ext_runner_source.py --check` if you touched the runner,
  and `node --check` on any JS you changed. CI fails on drift.
- Keep the core free of extension specifics, and keep code comments to one line.
