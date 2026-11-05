/**
 * Each ui component mounted in its canonical composition, opened, driven by keyboard and checked
 * with axe: a missing part (an ItemText, a Title, a root around Command*), a bad nesting or a
 * selector that marks every item at once shows up here, before a screen uses it. A composition a
 * screen already proves (the journal's facet popover, the Invite dialog) is checked there.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/i18n";
import { expectAccessible } from "@/test/axe";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "./alert-dialog";
import { Button } from "./button";
import { Calendar } from "./calendar";
import { Checkbox } from "./checkbox";
import { Combobox, ComboboxContent, ComboboxEmpty, ComboboxInput, ComboboxItem, ComboboxList } from "./combobox";
import { CommandDialog, CommandInput, CommandItem, CommandList } from "./command";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Label } from "./label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "./sheet";
import { Switch } from "./switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { ToggleGroup, ToggleGroupItem } from "./toggle-group";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./tooltip";

const ROOMS = ["salon", "cuisine", "bureau"];

function mount(ui: React.ReactNode) {
  return render(
    <I18nProvider initial="fr">
      <TooltipProvider>{ui}</TooltipProvider>
    </I18nProvider>,
  );
}

const highlighted = (root: HTMLElement) =>
  within(root)
    .queryAllByRole("option")
    .filter((o) => o.hasAttribute("data-highlighted") && o.getAttribute("data-highlighted") !== "false");

describe("ui components in their canonical composition", () => {
  it("Select: opens from the keyboard, highlights one item at a time, chooses with Enter", async () => {
    const user = userEvent.setup();
    function Example() {
      const [room, setRoom] = useState("salon");
      return (
        <>
          <Label htmlFor="room">Pièce</Label>
          <Select
            value={room}
            onValueChange={(v) => v && setRoom(v)}
            items={ROOMS.map((r) => ({ value: r, label: r }))}
          >
            <SelectTrigger id="room">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROOMS.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <output>{room}</output>
        </>
      );
    }
    mount(<Example />);
    screen.getByRole("combobox", { name: "Pièce" }).focus();
    await user.keyboard("{ArrowDown}");
    const list = await screen.findByRole("listbox");
    await waitFor(() => expect(highlighted(list)).toHaveLength(1));
    await user.keyboard("{ArrowDown}");
    expect(highlighted(list)).toHaveLength(1);
    await expectAccessible();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("cuisine"));
  });

  it("Combobox: filters as one types, Enter picks the highlighted item", async () => {
    const user = userEvent.setup();
    function Example() {
      const [room, setRoom] = useState<string | null>(null);
      return (
        <>
          <Label htmlFor="pick">Pièce</Label>
          <Combobox items={ROOMS} value={room} onValueChange={setRoom}>
            <ComboboxInput id="pick" placeholder="Choisir…" />
            <ComboboxContent>
              <ComboboxEmpty>Aucune pièce.</ComboboxEmpty>
              <ComboboxList>
                {(r: string) => (
                  <ComboboxItem key={r} value={r}>
                    {r}
                  </ComboboxItem>
                )}
              </ComboboxList>
            </ComboboxContent>
          </Combobox>
          <output>{room}</output>
        </>
      );
    }
    mount(<Example />);
    await user.type(screen.getByRole("combobox", { name: "Pièce" }), "cui");
    const list = await screen.findByRole("listbox");
    expect(
      within(list)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["cuisine"]);
    await user.keyboard("{ArrowDown}");
    expect(highlighted(list)).toHaveLength(1);
    await expectAccessible();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("cuisine"));
  });

  it("CommandDialog: a named dialog whose input and list share cmdk's root", async () => {
    const user = userEvent.setup();
    mount(
      <CommandDialog open onOpenChange={() => undefined} title="Aller à…" description="Chercher une section">
        <CommandInput placeholder="Aller à…" />
        <CommandList>
          <CommandItem value="journal">Journal</CommandItem>
          <CommandItem value="satellites">Satellites</CommandItem>
        </CommandList>
      </CommandDialog>,
    );
    expect(await screen.findByRole("dialog", { name: "Aller à…" })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Aller à…"), "sat");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Satellites"]);
    await expectAccessible();
  });

  it("AlertDialog: named, its cancel closes it", async () => {
    const user = userEvent.setup();
    mount(
      <AlertDialog>
        <AlertDialogTrigger render={<Button variant="destructive" />}>Révoquer…</AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Révoquer ce satellite ?</AlertDialogTitle>
            <AlertDialogDescription>Il ne pourra plus se connecter.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>,
    );
    await user.click(screen.getByRole("button", { name: "Révoquer…" }));
    expect(await screen.findByRole("alertdialog", { name: "Révoquer ce satellite ?" })).toBeInTheDocument();
    await expectAccessible();
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("Sheet: a named dialog with a close button", async () => {
    const user = userEvent.setup();
    mount(
      <Sheet>
        <SheetTrigger render={<Button />}>Connecter…</SheetTrigger>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Gmail</SheetTitle>
            <SheetDescription>Lire et chercher des courriels.</SheetDescription>
          </SheetHeader>
        </SheetContent>
      </Sheet>,
    );
    await user.click(screen.getByRole("button", { name: "Connecter…" }));
    const sheet = await screen.findByRole("dialog", { name: "Gmail" });
    await expectAccessible();
    await user.click(within(sheet).getByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("DropdownMenu: opens from the keyboard with one highlighted item", async () => {
    const user = userEvent.setup();
    mount(
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="outline" />}>Compte</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuGroup>
            <DropdownMenuLabel>mathis@lambert.family</DropdownMenuLabel>
            <DropdownMenuItem>Profil</DropdownMenuItem>
            <DropdownMenuItem>Se déconnecter</DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    screen.getByRole("button", { name: "Compte" }).focus();
    await user.keyboard("{Enter}");
    const menu = await screen.findByRole("menu");
    await user.keyboard("{ArrowDown}");
    const items = within(menu).getAllByRole("menuitem");
    await waitFor(() => expect(items.filter((i) => i.hasAttribute("data-highlighted"))).toHaveLength(1));
    await expectAccessible();
  });

  it("Tabs, ToggleGroup, Checkbox, Switch, Tooltip and Calendar are labelled and keyboard-driven", async () => {
    const user = userEvent.setup();
    mount(
      <>
        <Tabs defaultValue="apercu">
          <TabsList aria-label="Sections de la connexion">
            <TabsTrigger value="apercu">Aperçu</TabsTrigger>
            <TabsTrigger value="outils">Outils</TabsTrigger>
          </TabsList>
          <TabsContent value="apercu">Résumé</TabsContent>
          <TabsContent value="outils">Liste</TabsContent>
        </Tabs>
        <ToggleGroup aria-label="Densité" value={["confortable"]}>
          <ToggleGroupItem value="confortable">Confortable</ToggleGroupItem>
          <ToggleGroupItem value="compact">Compact</ToggleGroupItem>
        </ToggleGroup>
        <Label htmlFor="c1">
          <Checkbox id="c1" /> Demander confirmation
        </Label>
        <Label htmlFor="s1">
          <Switch id="s1" /> mail_send
        </Label>
        <Tooltip>
          <TooltipTrigger render={<Button variant="ghost" />}>Réduire</TooltipTrigger>
          <TooltipContent>Réduire · ⌘B</TooltipContent>
        </Tooltip>
        <Calendar mode="single" />
      </>,
    );
    screen.getByRole("tab", { name: "Aperçu" }).focus();
    // Base UI moves focus and commits state on the next frame: wait for it as a person would
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Outils" })).toHaveFocus());
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Outils" })).toHaveAttribute("aria-selected", "true"));
    await user.click(screen.getByRole("checkbox", { name: /Demander confirmation/ }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /Demander confirmation/ })).toBeChecked());
    await user.click(screen.getByRole("switch", { name: /mail_send/ }));
    await waitFor(() => expect(screen.getByRole("switch", { name: /mail_send/ })).toBeChecked());
    await expectAccessible();
  });
});
