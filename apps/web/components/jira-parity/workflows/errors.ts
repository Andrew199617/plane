/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: helpers for forbidden (HTTP 403) responses of the workflow / agent guard.
// The API services throw `error.response.data`, which for these responses is {"error": "...", "code": "..."}.
import type { TJiraParityApiError } from "@plane/types";

/** Narrows an API error body to the jira-parity {error, code} shape. */
export const isJiraParityApiError = (error: unknown): error is TJiraParityApiError =>
  !!error &&
  typeof error === "object" &&
  typeof (error as Record<string, unknown>).code === "string" &&
  typeof (error as Record<string, unknown>).error === "string";

/**
 * Returns the server's message for a forbidden transition / agent action (e.g. "You can't move this
 * work item from 'To Do' to 'Done'."), or undefined for any other error.
 */
export const getJiraParityForbiddenMessage = (error: unknown): string | undefined =>
  isJiraParityApiError(error) ? error.error : undefined;
