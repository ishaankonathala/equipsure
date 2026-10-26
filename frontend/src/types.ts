export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface CurrentUser {
  id: string
  email: string
  full_name: string
  role: string
  business_id: string | null
  is_active: boolean
}

export interface ClaimSummary {
  id: string
  reference: string
  business_id: string
  policy_id: string
  equipment_id: string
  status: string
  incident_date: string
  amount_claimed: string
}