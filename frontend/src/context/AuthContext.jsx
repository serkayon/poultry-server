import React, { createContext, useContext, useMemo, useState } from 'react'
import { clearAuthSession, getAuthUser, setAuthSession } from '../api/client'

const AuthContext = createContext(null)

const DEFAULT_USER = { full_name: 'User', company_name: 'Poultry Farm' }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => getAuthUser() || DEFAULT_USER)

  const login = (token, nextUser) => {
    const resolvedUser = nextUser && typeof nextUser === 'object' ? nextUser : DEFAULT_USER
    setAuthSession(token, resolvedUser)
    setUser(resolvedUser)
  }

  const logout = () => {
    clearAuthSession()
    setUser(DEFAULT_USER)
  }

  const value = useMemo(
    () => ({ user, loading: false, login, logout }),
    [user]
  )

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
