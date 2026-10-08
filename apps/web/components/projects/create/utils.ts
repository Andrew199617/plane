/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { RANDOM_EMOJI_CODES } from "@plane/constants";
import type { IProject } from "@plane/types";
import { getRandomCoverImage } from "@/helpers/cover-image.helper";

// jira-parity: the project lead defaults to the current user (pass their id)
export const getProjectFormValues = (projectLeadId: string | null = null): Partial<IProject> => ({
  cover_image_url: getRandomCoverImage(),
  description: "",
  logo_props: {
    in_use: "emoji",
    emoji: {
      value: RANDOM_EMOJI_CODES[Math.floor(Math.random() * RANDOM_EMOJI_CODES.length)],
    },
  },
  identifier: "",
  name: "",
  network: 2,
  project_lead: projectLeadId,
});
