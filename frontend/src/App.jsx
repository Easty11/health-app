import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import CheckIn from './pages/CheckIn'
import CheckInAM from './pages/CheckInAM'
import NightlyCloseOut from './pages/NightlyCloseOut'
import Metrics from './pages/Metrics'
import InterpretationView from './pages/InterpretationView'

function RequireAuth({ children }) {
  return localStorage.getItem('token') ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/checkin" element={<RequireAuth><CheckIn /></RequireAuth>} />
        <Route path="/checkin-am" element={<RequireAuth><CheckInAM /></RequireAuth>} />
        <Route path="/nightly" element={<RequireAuth><NightlyCloseOut /></RequireAuth>} />
        <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/metrics" element={<RequireAuth><Metrics /></RequireAuth>} />
        <Route path="/interpretation" element={<RequireAuth><InterpretationView /></RequireAuth>} />
        <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
