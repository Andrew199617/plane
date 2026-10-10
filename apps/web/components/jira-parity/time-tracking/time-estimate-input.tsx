/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: inline Jira-style duration editor ("1w 2d 4h 30m") for Issue.original_estimate /
// remaining_estimate (minutes). Shows the formatted value as a trigger button; clicking it swaps in a
// text input. Enter / blur saves, Escape cancels, an empty value clears the estimate.
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { observer } from "mobx-react";
// plane imports
import { getSelectClassName, SelectTriggerChrome, triggerVariants } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// hooks
import { useTimeTracking } from "@/hooks/store/jira-parity/use-time-tracking";
// local imports
import { formatDuration, parseDuration } from "./duration";

export type TTimeEstimateInputVariant = "select-ghost-md" | "table-cell";

export type TTimeEstimateInputProps = {
  /** Current estimate in minutes (null / undefined = unset). */
  value: number | null | undefined;
  /** Called with the new estimate in minutes (null clears it); only when the value changed. */
  onChange: (minutes: number | null) => void | Promise<void>;
  /** Accessible name of the field, e.g. "Original estimate". */
  label: string;
  placeholder: string;
  disabled?: boolean;
  variant?: TTimeEstimateInputVariant;
  /** Extra classes for the trigger button (the spreadsheet passes `clickable`). */
  className?: string;
  testId?: string;
  /** Called when editing ends (the spreadsheet refocuses its cell). */
  onClose?: () => void;
};

export const TimeEstimateInput = observer(function TimeEstimateInput(props: TTimeEstimateInputProps) {
  const {
    value,
    onChange,
    label,
    placeholder,
    disabled = false,
    variant = "select-ghost-md",
    className,
    testId,
    onClose,
  } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { config } = useTimeTracking();
  // states
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [isInvalid, setIsInvalid] = useState(false);
  // refs
  const inputRef = useRef<HTMLInputElement>(null);
  // set when Enter / Escape already finished the edit, so the blur that follows is ignored
  const isFinishedRef = useRef(false);
  // derived values
  const formattedValue = formatDuration(value, config);
  const isTableCell = variant === "table-cell";

  useEffect(() => {
    if (!isEditing) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [isEditing]);

  const startEditing = () => {
    if (disabled) return;
    isFinishedRef.current = false;
    setDraft(formattedValue);
    setIsInvalid(false);
    setIsEditing(true);
  };

  const stopEditing = () => {
    isFinishedRef.current = true;
    setIsEditing(false);
    setIsInvalid(false);
    onClose?.();
  };

  /** Saves the draft. Returns false (and keeps the editor open) when the draft can't be parsed. */
  const commit = (): boolean => {
    const result = parseDuration(draft, config);
    if (!result.ok) {
      setIsInvalid(true);
      return false;
    }
    stopEditing();
    if (result.minutes !== (value ?? null)) void onChange(result.minutes);
    return true;
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      commit();
    } else if (event.key === "Escape") {
      // keep Escape from also closing the surrounding peek overview / modal
      event.preventDefault();
      event.stopPropagation();
      stopEditing();
    }
  };

  const handleBlur = () => {
    if (isFinishedRef.current) return;
    if (commit()) return;
    // leaving the field with an invalid value discards the edit
    setToast({ type: "error", title: label, message: t("jp_time_tracking.invalid_format") });
    stopEditing();
  };

  if (isEditing) {
    return (
      <div className={cn("flex w-full flex-col gap-1", isTableCell && "h-full")}>
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            if (isInvalid) setIsInvalid(false);
          }}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          placeholder={t("jp_time_tracking.input_placeholder")}
          title={t("jp_time_tracking.input_hint")}
          aria-label={label}
          aria-invalid={isInvalid || undefined}
          data-invalid={isInvalid || undefined}
          data-testid={testId ? `${testId}-input` : undefined}
          autoComplete="off"
          spellCheck={false}
          className={
            isTableCell
              ? triggerVariants({
                  variant: "table-cell",
                  isActive: true,
                  className: cn(
                    "h-full bg-transparent text-primary placeholder:text-placeholder",
                    isInvalid && "ring-1 ring-danger-strong ring-inset"
                  ),
                })
              : getSelectClassName("select", "md", true, "w-full placeholder:text-placeholder")
          }
        />
        {!isTableCell && isInvalid && (
          <span role="alert" className="text-caption-sm-regular text-danger-primary">
            {t("jp_time_tracking.invalid_format")}
          </span>
        )}
      </div>
    );
  }

  return (
    <SelectTriggerChrome
      variant={variant}
      disabled={disabled}
      isEmpty={!formattedValue}
      appendIcon={null}
      onClick={startEditing}
      aria-label={formattedValue ? `${label}: ${formattedValue}` : label}
      title={disabled ? undefined : t("jp_time_tracking.input_hint")}
      data-testid={testId}
      className={className}
    >
      <span className={cn("truncate", !formattedValue && "text-placeholder")}>{formattedValue || placeholder}</span>
    </SelectTriggerChrome>
  );
});
