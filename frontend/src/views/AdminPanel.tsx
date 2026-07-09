import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const AdminPanel = ({ onClose }: { onClose: () => void }) => {
  const [tName, setTName] = useState("");
  const [tSlug, setTSlug] = useState("");
  const [tMsg, setTMsg] = useState<string | null>(null);

  const [uTenantId, setUTenantId] = useState("");
  const [uEmail, setUEmail] = useState("");
  const [uPassword, setUPassword] = useState("");
  const [uMsg, setUMsg] = useState<string | null>(null);

  const createTenant = async (e: FormEvent) => {
    e.preventDefault();
    setTMsg(null);
    const res = await fetch("/api/admin/tenants", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: tName, slug: tSlug }),
    });
    const data = (await res.json()) as { tenant?: { tenant_id: number }; detail?: string };
    setTMsg(
      res.ok && data.tenant
        ? `Created tenant #${data.tenant.tenant_id} (${tSlug}).`
        : `Failed: ${data.detail ?? res.status}`
    );
    if (res.ok && data.tenant) setUTenantId(String(data.tenant.tenant_id));
  };

  const createUser = async (e: FormEvent) => {
    e.preventDefault();
    setUMsg(null);
    const res = await fetch(`/api/admin/tenants/${uTenantId}/users`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: uEmail, password: uPassword }),
    });
    const data = (await res.json()) as { user?: { user_id: number }; detail?: string };
    setUMsg(
      res.ok && data.user
        ? `Created user #${data.user.user_id} for tenant ${uTenantId}.`
        : `Failed: ${data.detail ?? res.status}`
    );
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Create tenant</CardTitle>
          <CardDescription>Provision a new client organization.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-3" onSubmit={createTenant}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tName">Name</Label>
              <Input id="tName" onChange={(e) => setTName(e.target.value)} required value={tName} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tSlug">Slug</Label>
              <Input id="tSlug" onChange={(e) => setTSlug(e.target.value)} required value={tSlug} />
            </div>
            {tMsg && <p className="text-sm text-muted-foreground">{tMsg}</p>}
            <Button className="self-start" type="submit">
              Create tenant
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Create tenant admin</CardTitle>
          <CardDescription>Add the first login for a tenant.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-3" onSubmit={createUser}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="uTenantId">Tenant id</Label>
              <Input
                id="uTenantId"
                onChange={(e) => setUTenantId(e.target.value)}
                required
                type="number"
                value={uTenantId}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="uEmail">Email</Label>
              <Input
                id="uEmail"
                onChange={(e) => setUEmail(e.target.value)}
                required
                type="email"
                value={uEmail}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="uPassword">Password</Label>
              <Input
                id="uPassword"
                onChange={(e) => setUPassword(e.target.value)}
                required
                type="password"
                value={uPassword}
              />
            </div>
            {uMsg && <p className="text-sm text-muted-foreground">{uMsg}</p>}
            <Button className="self-start" type="submit">
              Create user
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={onClose} variant="ghost">
          Close
        </Button>
      </div>
    </div>
  );
};
