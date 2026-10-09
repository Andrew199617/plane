// oxlint-disable promise/always-return
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
// types
import { setToast } from "@plane/blocks/toast";
import type { ICycle, TCycleTabOptions } from "@plane/types";
// ui
import { Dialog, DialogContent } from "@makeplane/propel/components/dialog";
// hooks
import { renderFormattedPayloadDate } from "@plane/utils";
import { useCycle } from "@/hooks/store/use-cycle";
import { useProject } from "@/hooks/store/use-project";
import useLocalStorage from "@/hooks/use-local-storage";
import { usePlatformOS } from "@/hooks/use-platform-os";
// services
import { CycleService } from "@/services/cycle.service";
// local imports
import { CycleForm } from "./form";

type CycleModalProps = {
  isOpen: boolean;
  handleClose: () => void;
  data?: ICycle | null;
  workspaceSlug: string;
  projectId: string;
};

// services
const cycleService = new CycleService();

export function CycleCreateUpdateModal(props: CycleModalProps) {
  const { isOpen, handleClose, data, workspaceSlug, projectId } = props;
  // states
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [nextSprintName, setNextSprintName] = useState<string | undefined>(undefined);
  // store hooks
  const { workspaceProjectIds } = useProject();
  const { createCycle, updateCycleDetails } = useCycle();
  const { isMobile } = usePlatformOS();

  const { setValue: setCycleTab } = useLocalStorage<TCycleTabOptions>("cycle_tab", "active");

  const handleCreateCycle = async (payload: Partial<ICycle>) => {
    if (!workspaceSlug || !projectId) return;

    const selectedProjectId = payload.project_id ?? projectId.toString();
    // jira-parity: a new sprint is always a future sprint (it only becomes active via "Start sprint")
    await createCycle(workspaceSlug, selectedProjectId, payload)
      .then((_res) => {
        setToast({
          type: "success",
          title: "Success!",
          message: "Sprint created successfully.",
        });
      })
      .catch((err) => {
        setToast({
          type: "error",
          title: "Error!",
          message: err?.detail ?? "Error in creating sprint. Please try again.",
        });
      });
  };

  const handleUpdateCycle = async (cycleId: string, payload: Partial<ICycle>) => {
    if (!workspaceSlug || !projectId) return;

    const selectedProjectId = payload.project_id ?? projectId.toString();
    await updateCycleDetails(workspaceSlug, selectedProjectId, cycleId, payload)
      .then((_res) => {
        setToast({
          type: "success",
          title: "Success!",
          message: "Sprint updated successfully.",
        });
      })
      .catch((err) => {
        setToast({
          type: "error",
          title: "Error!",
          message: err?.detail ?? "Error in updating sprint. Please try again.",
        });
      });
  };

  const handleFormSubmit = async (formData: Partial<ICycle>) => {
    if (!workspaceSlug || !projectId) return;

    const payload: Partial<ICycle> = {
      ...formData,
      start_date: renderFormattedPayloadDate(formData.start_date) ?? null,
      end_date: renderFormattedPayloadDate(formData.end_date) ?? null,
    };

    // jira-parity: overlapping sprint dates are allowed (no date-check round trip); dates stay optional
    if (data?.id) await handleUpdateCycle(data.id, payload);
    else {
      await handleCreateCycle(payload).then(() => {
        setCycleTab("all");
      });
    }
    handleClose();
  };

  // jira-parity: a new sprint's name continues the project's "<series> Sprint N" naming
  useEffect(() => {
    if (!isOpen || data || !workspaceSlug || !activeProject) {
      setNextSprintName(undefined);
      return;
    }
    let isCurrent = true;
    const fetchNextSprintName = async () => {
      try {
        const response = await cycleService.getNextSprintName(workspaceSlug, activeProject);
        if (isCurrent && response?.name) setNextSprintName(response.name);
      } catch {
        // no suggestion: the name field simply stays empty
      }
    };
    void fetchNextSprintName();
    return () => {
      isCurrent = false;
    };
  }, [isOpen, data, workspaceSlug, activeProject]);

  useEffect(() => {
    // if modal is closed, reset active project to null
    // and return to avoid activeProject being set to some other project
    if (!isOpen) {
      setActiveProject(null);
      return;
    }

    // if data is present, set active project to the project of the
    // issue. This has more priority than the project in the url.
    if (data && data.project_id) {
      setActiveProject(data.project_id);
      return;
    }

    // if data is not present, set active project to the project
    // in the url. This has the least priority.
    if (workspaceProjectIds && workspaceProjectIds.length > 0 && !activeProject)
      setActiveProject(projectId ?? workspaceProjectIds?.[0] ?? null);
  }, [activeProject, data, projectId, workspaceProjectIds, isOpen]);

  return (
    <Dialog
      open={isOpen}
      // The legacy modal shell had no `handleClose`, so an outside press never dismissed it and
      // Escape came from `useKeypress`; Base UI's own Escape now reaches the same handler.
      disablePointerDismissal
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent size="md">
        <CycleForm
          handleFormSubmit={handleFormSubmit}
          handleClose={handleClose}
          status={!!data}
          projectId={activeProject ?? ""}
          setActiveProject={setActiveProject}
          data={data}
          isMobile={isMobile}
          defaultName={nextSprintName}
        />
      </DialogContent>
    </Dialog>
  );
}
