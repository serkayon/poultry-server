import React, { createContext, useContext, useState } from 'react'

const AuthContext = createContext(null)

const DEFAULT_USER = { full_name: 'User', company_name: 'Poultry Farm' }

export function AuthProvider({ children }) {
  const [user] = useState(DEFAULT_USER)

  return (
    <AuthContext.Provider value={{ user, loading: false }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
