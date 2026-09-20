# NABZ Instagram V1

This module is isolated from the existing Telegram V13 runtime.

## Goal
Prepare Persian news content for Instagram and publish through Meta's official Instagram API when the required account/app secrets are configured.

## Current phase
- News/content preparation: enabled
- Persian-only validation: enabled
- Duplicate protection: enabled
- Instagram publishing: guarded; it will not publish until the required GitHub secrets are present
- Dry-run mode: enabled by default

## Required GitHub Secrets for publishing
- INSTAGRAM_ACCESS_TOKEN
- INSTAGRAM_USER_ID

Do not commit tokens to the repository.

## Publishing model
The official Instagram API uses a media-container flow: create media, wait for processing, then publish. The workflow in this directory keeps that integration isolated so Telegram V13 is not modified.
