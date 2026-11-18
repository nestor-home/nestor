import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { type CatalogueSearch, CatalogueView } from "@/features/connections/catalogue-view";

const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);

export const Route = createFileRoute("/_app/connections/catalogue")({
  validateSearch: (search: Record<string, unknown>): CatalogueSearch => {
    const [connect, replaces, preset] = [text(search.connect), text(search.replaces), text(search.preset)];
    const owner = text(search.owner);
    return {
      ...(connect ? { connect } : {}),
      ...(replaces ? { replaces } : {}),
      ...(preset ? { preset } : {}),
      ...(owner ? { owner } : {}),
    };
  },
  component: CataloguePage,
});

function CataloguePage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="connections:read">
      <CatalogueView search={search} onSearch={(next) => void navigate({ search: next })} />
    </Guard>
  );
}
