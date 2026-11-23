import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type User = Schemas["UserOut"];
export type Role = Schemas["RoleOut"];
export type Grant = Schemas["GrantOut"];
export type GrantIn = Schemas["GrantIn"];
export type Options = Schemas["OptionsOut"];
export type Invite = Schemas["InviteOut"];
export type UserUpdate = Schemas["UserUpdateIn"];

const USERS = ["admin", "users"] as const;
const ROLES = ["admin", "roles"] as const;

export const useUsers = () =>
  useQuery({ queryKey: USERS, queryFn: () => call(api.GET("/api/v1/admin/users")) });

export const useRoles = () =>
  useQuery({ queryKey: ROLES, queryFn: () => call(api.GET("/api/v1/admin/roles")) });

export const useOptions = () =>
  useQuery({
    queryKey: ["admin", "options"],
    queryFn: () => call(api.GET("/api/v1/admin/options")),
    staleTime: Infinity,
  });

/** After any change: users and roles both show role membership. */
function useRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: USERS }),
      qc.invalidateQueries({ queryKey: ROLES }),
      // Your own roles may have changed what you can see.
      qc.invalidateQueries({ queryKey: ["me"] }),
    ]);
  };
}

export function useInviteUser() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: Schemas["UserCreateIn"]) =>
      call(api.POST("/api/v1/admin/users", { body })),
    onSuccess: refresh,
  });
}

export function useUpdateUser(userId: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: UserUpdate) =>
      call(
        api.PATCH("/api/v1/admin/users/{user_id}", {
          params: { path: { user_id: userId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export function useUserAction(userId: string) {
  const refresh = useRefresh();
  const path = { params: { path: { user_id: userId } } };
  return {
    reinvite: useMutation({
      mutationFn: () => call(api.POST("/api/v1/admin/users/{user_id}/invite", path)),
      onSuccess: refresh,
    }),
    resetTotp: useMutation({
      mutationFn: () => call(api.POST("/api/v1/admin/users/{user_id}/reset-totp", path)),
      onSuccess: refresh,
    }),
    unlock: useMutation({
      mutationFn: () => call(api.POST("/api/v1/admin/users/{user_id}/unlock", path)),
      onSuccess: refresh,
    }),
  };
}

export function useCreateRole() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: Schemas["RoleCreateIn"]) => call(api.POST("/api/v1/admin/roles", { body })),
    onSuccess: refresh,
  });
}

export function useRoleActions(roleId: string) {
  const refresh = useRefresh();
  const path = { params: { path: { role_id: roleId } } };
  return {
    updateDescription: useMutation({
      mutationFn: (description: string) =>
        call(api.PATCH("/api/v1/admin/roles/{role_id}", { ...path, body: { description } })),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: () => call(api.DELETE("/api/v1/admin/roles/{role_id}", path)),
      onSuccess: refresh,
    }),
    addGrant: useMutation({
      mutationFn: (body: GrantIn) =>
        call(api.POST("/api/v1/admin/roles/{role_id}/grants", { ...path, body })),
      onSuccess: refresh,
    }),
  };
}

export function useRemoveGrant() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (grantId: string) =>
      call(api.DELETE("/api/v1/admin/grants/{grant_id}", { params: { path: { grant_id: grantId } } })),
    onSuccess: refresh,
  });
}

/** The link a new person opens. The token goes in the fragment, never to a server. */
export function inviteLink(token: string): string {
  return `${window.location.origin}/invite#${token}`;
}
