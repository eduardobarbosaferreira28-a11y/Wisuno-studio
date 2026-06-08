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
        <div className="p-6 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#FF6B00] rounded-md flex items-center justify-center font-black text-white text-lg">
              W
            </div>
            <div>
              <div className="font-brand font-black text-lg leading-tight tracking-[-0.3px] text-white">Wisuno</div>
              <div className="text-[10px] font-medium text-[#666666] uppercase tracking-widest mt-[2px]">Studio</div>
            </div>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto py-3">
          <div className="text-[10px] font-semibold text-[#666666] uppercase tracking-[1.2px] px-6 pb-2 pt-3">
            Main Menu
          </div>
          <div className="flex flex-col gap-0 px-0">
            {navItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => 
                  `flex items-center gap-3 px-6 py-2.5 transition-colors text-[13px] font-medium relative ${
                    isActive 
                      ? 'bg-[rgba(255,107,0,0.08)] text-[#FF6B00]' 
                      : 'text-[#AAAAAA] hover:bg-[#1C1C1C] hover:text-white'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && <div className="absolute left-0 top-1 bottom-1 w-[3px] bg-[#FF6B00] rounded-r-sm" />}
                    <div className={isActive ? 'opacity-100' : 'opacity-70'}>{item.icon}</div>
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </div>

        <div className="p-4 border-t border-white/5">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 w-full rounded-md transition-colors text-[13px] font-medium text-[#AAAAAA] hover:bg-destructive/10 hover:text-destructive"
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
