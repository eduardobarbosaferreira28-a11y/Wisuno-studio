import { Outlet, NavLink } from 'react-router-dom'
import { Home, Settings, Images, Video, LogOut } from 'lucide-react'
import { supabase } from '@/lib/supabase'

export const Layout = () => {
  const handleLogout = async () => {
    await supabase.auth.signOut()
    window.location.href = '/login'
  }

  const navItems = [
    { to: '/', icon: <Home className="w-4 h-4" />, label: 'Dashboard' },
    { to: '/carousel', icon: <Images className="w-4 h-4" />, label: 'Carousel Studio' },
    { to: '/video', icon: <Video className="w-4 h-4" />, label: 'Video Studio' },
    { to: '/setup', icon: <Settings className="w-4 h-4" />, label: 'Setup' },
  ]

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <div className="w-60 min-w-60 bg-card border-r border-border flex flex-col">
        <div className="p-5 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-primary rounded flex items-center justify-center font-bold text-white">
              W
            </div>
            <div>
              <div className="font-black text-lg leading-tight tracking-tight">Wisuno</div>
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">Studio</div>
            </div>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto py-3">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-5 pb-2">
            Main Menu
          </div>
          <div className="flex flex-col gap-1 px-3">
            {navItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => 
                  `flex items-center gap-3 px-3 py-2 rounded-md transition-colors text-sm font-medium ${
                    isActive 
                      ? 'bg-primary/10 text-primary' 
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                  }`
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>

        <div className="p-3 border-t border-border">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 w-full rounded-md transition-colors text-sm font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </button>
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-8 relative">
        <div className="max-w-4xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
