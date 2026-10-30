import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, keys, type PairingRequest } from "@/api";
import { Dither } from "@/components/dither";
import { Field } from "@/components/field";
import { useNotify } from "@/components/notices";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";
import { CAPABILITY_ICON } from "@/lib/icons";

const CODE = /^\d{6}$/;

/** What the person typed, as the code: spaces and dashes people add while reading are ignored. */
export function normaliseCode(typed: string): string {
  return typed.replace(/[\s-]/g, "");
}

/**
 * Approving needs the code the device shows: it proves the person approving can see the device.
 * The code is never displayed here. What the satellite may do can be narrowed now.
 */
export function ApproveForm({ request, onDone }: { request: PairingRequest; onDone?: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [code, setCode] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  const [granted, setGranted] = useState(() => new Set(request.capabilities.map((c) => c.name)));
  const approve = useMutation({
    mutationFn: () =>
      api.approve(request.id, {
        code: normaliseCode(code),
        capabilities: [...granted].sort(),
      }),
    onSuccess: (satellite) => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      notify(t("sat-paired-notice", { id: satellite.id, room: satellite.room }));
      onDone?.();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!CODE.test(normaliseCode(code))) {
      setInvalid(t("sat-code-invalid"));
      return;
    }
    setInvalid(null);
    approve.mutate();
  }

  const codeId = `code-${request.id}`;
  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <div className="relative overflow-hidden rounded-md border border-rule bg-paper-sunken px-5 py-5">
        <Dither shape="vignette" from={0.05} to={0.5} dot={2} className="absolute inset-0 size-full text-ink/20" />
        <Field label={t("sat-code-label")} htmlFor={codeId} error={invalid} className="relative">
          <Input
            id={codeId}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={9}
            placeholder="000 000"
            aria-invalid={invalid ? true : undefined}
            aria-describedby={invalid ? `${codeId}-error` : undefined}
            className="h-12 w-48 bg-paper-raised font-mono text-2xl tracking-[0.35em]"
            spellCheck={false}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1 text-[0.8rem] font-medium">{t("sat-grant-legend")}</legend>
        <p className="mb-2 text-xs text-ink-muted">{t("sat-grant-hint")}</p>
        {request.capabilities.length === 0 ? (
          <p className="text-sm text-ink-muted">{t("sat-grant-none")}</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {request.capabilities.map((c) => {
              const id = `${request.id}-${c.name}`;
              return (
                <li key={c.name}>
                  <label htmlFor={id} className="flex items-start gap-2.5">
                    <Checkbox
                      id={id}
                      checked={granted.has(c.name)}
                      onCheckedChange={(on) =>
                        setGranted((current) => {
                          const next = new Set(current);
                          if (on) next.add(c.name);
                          else next.delete(c.name);
                          return next;
                        })
                      }
                      className="mt-0.5"
                    />
                    <span className="flex items-start gap-2 text-sm">
                      {(() => {
                        const Icon = CAPABILITY_ICON[c.name];
                        return Icon ? <Icon className="mt-0.5 size-3.5 text-ink-muted" aria-hidden="true" /> : null;
                      })()}
                      <span>
                        {c.label} <code className="block text-[0.7rem] text-ink-faint">{c.name}</code>
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </fieldset>
      <FormError error={approve.error} />
      <div className="flex justify-end">
        <Button type="submit" disabled={approve.isPending}>
          {approve.isPending ? t("sat-pairing") : t("sat-pair")}
        </Button>
      </div>
    </form>
  );
}
