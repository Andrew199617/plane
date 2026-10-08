/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item type picker (owned by the work-item-types feature), built on the generic
// single-select `Select` from @plane/blocks. Used by the create/edit modal, the detail sidebar, the peek
// overview, the spreadsheet column and the header switcher.
import { useMemo } from "react";
import { observer } from "mobx-react";
// plane imports
import { WorkItemsOutline } from "@makeplane/propel/icons";
import { Select } from "@plane/blocks/select";
import type { SelectVariant } from "@plane/blocks/select";
import { useTranslation } from "@plane/i18n";
import type { TWorkItemType } from "@plane/types";
// hooks
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
// local imports
import { WorkItemTypeIcon } from "./icons";

export type TWorkItemTypeSelectProps = {
  /** Selected work item type id. */
  value: string | null | undefined;
  /** Emits the picked work item type id. */
  onChange: (workItemTypeId: string) => void;
  variant: SelectVariant;
  disabled?: boolean;
  /** Return a reason to show an option dimmed and non-selectable (the reason is shown at the row end). */
  getOptionDisabledReason?: (workItemType: TWorkItemType) => string | undefined;
  placeholder?: string;
  /** Shows the trigger tooltip (heading "Type" + the selected type). */
  tooltip?: boolean;
  /** Renders the type name next to the icon in the trigger. Defaults to true. */
  showLabel?: boolean;
  className?: string;
  onClose?: () => void;
  testId?: string;
  tabIndex?: number;
};

export const WorkItemTypeSelect = observer(function WorkItemTypeSelect(props: TWorkItemTypeSelectProps) {
  const {
    value,
    onChange,
    variant,
    disabled = false,
    getOptionDisabledReason,
    placeholder,
    tooltip = false,
    showLabel = true,
    className,
    onClose,
    testId,
    tabIndex,
  } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { activeWorkItemTypes, getWorkItemTypeById } = useWorkItemTypes();
  // derived values
  const selectedType = getWorkItemTypeById(value) ?? null;
  const placeholderText = placeholder ?? t("jp_work_item_types.select.placeholder");
  // inactive types stay visible when they are the current selection
  const options = useMemo(
    () => (selectedType && !selectedType.is_active ? [...activeWorkItemTypes, selectedType] : activeWorkItemTypes),
    [activeWorkItemTypes, selectedType]
  );

  return (
    <Select<TWorkItemType>
      getValues={() => options}
      value={selectedType}
      onChange={(workItemTypeId) => {
        if (!workItemTypeId || workItemTypeId === value) return;
        onChange(workItemTypeId);
      }}
      disabled={disabled}
      placeholder={placeholderText}
      showSearch={options.length > 8}
      pinSelected={false}
      onClose={onClose}
      emptyMessage={t("jp_work_item_types.select.empty")}
      getOptionValue={(workItemType) => workItemType.id}
      getOptionLabel={(workItemType) => workItemType.name}
      getOptionIcon={(workItemType) => <WorkItemTypeIcon workItemType={workItemType} className="size-4" />}
      getOptionDisabled={
        getOptionDisabledReason ? (workItemType) => getOptionDisabledReason(workItemType) !== undefined : undefined
      }
      getOptionTrailing={
        getOptionDisabledReason
          ? (workItemType) => {
              const reason = getOptionDisabledReason(workItemType);
              return reason ? (
                <span className="truncate text-caption-sm-regular text-tertiary">{reason}</span>
              ) : undefined;
            }
          : undefined
      }
    >
      <Select.Trigger<TWorkItemType>
        disabled={disabled}
        variant={variant}
        tabIndex={tabIndex}
        className={className}
        data-testid={testId}
        prependIcon={(selected) =>
          selected[0] ? <WorkItemTypeIcon workItemType={selected[0]} /> : <WorkItemsOutline />
        }
        label={(selected) => selected[0]?.name ?? placeholderText}
        tooltip={
          tooltip
            ? { heading: t("jp_work_item_types.property_label"), emptyContent: t("jp_work_item_types.select.none") }
            : undefined
        }
      >
        {(selected) => {
          if (!showLabel) return null;
          const label = selected[0]?.name ?? placeholderText;
          return <span className="min-w-0 grow truncate text-left">{label}</span>;
        }}
      </Select.Trigger>
    </Select>
  );
});
