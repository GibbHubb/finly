import api from "./api";
import type {
  CategorisationRule,
  CategorisationRuleCreate,
  CategorisationRuleUpdate,
} from "@/types";

export const rulesService = {
  async list(): Promise<CategorisationRule[]> {
    const { data } = await api.get<CategorisationRule[]>("/categorisation-rules/");
    return data;
  },

  async create(payload: CategorisationRuleCreate): Promise<CategorisationRule> {
    const { data } = await api.post<CategorisationRule>("/categorisation-rules/", payload);
    return data;
  },

  async update(id: number, payload: CategorisationRuleUpdate): Promise<CategorisationRule> {
    const { data } = await api.patch<CategorisationRule>(`/categorisation-rules/${id}`, payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/categorisation-rules/${id}`);
  },

  async applyNow(): Promise<{ updated: number }> {
    const { data } = await api.post<{ updated: number }>("/categorisation-rules/apply");
    return data;
  },
};
