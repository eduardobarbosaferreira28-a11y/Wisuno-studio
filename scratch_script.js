
    // Password toggle
    const togglePassword = document.getElementById('togglePassword');
    const passwordInput = document.getElementById('password');
    const eyeIcon = document.getElementById('eyeIcon');
    
    togglePassword.addEventListener('click', function () {
      const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
      passwordInput.setAttribute('type', type);
      
      if (type === 'text') {
        eyeIcon.innerHTML = `
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
          <line x1="1" y1="1" x2="23" y2="23"></line>
        `;
      } else {
        eyeIcon.innerHTML = `
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        `;
      }
    });
    // These keys are public and safe to expose to the frontend.
    // They are injected dynamically by the backend, or you can hardcode them here 
    // since they are safe. For now we will fetch them from the setup endpoint,
    // or you can just replace them below.
    
    // Fallback keys if you want to hardcode them directly:
    const SUPABASE_URL = "https://wkfwjdwjpavgzugwcgte.supabase.co";
    const SUPABASE_ANON_KEY = "sb_publishable_ch--T1W0Vpg1ULGdQH8e2g_U-rNgiiF";
    
    const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('email').value;
      const password = document.getElementById('password').value;
      const errorMsg = document.getElementById('errorMsg');
      const btn = document.querySelector('.login-btn');
      
      btn.textContent = "Logging in...";
      btn.disabled = true;
      errorMsg.style.display = 'none';
      
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email,
        password: password,
      });
      
      if (error) {
        if (error.message.toLowerCase().includes("email not confirmed")) {
          errorMsg.innerHTML = "<strong>Email not confirmed!</strong><br>Please check your inbox and click the confirmation link sent by Supabase. Alternatively, you can disable 'Confirm email' in Supabase Auth settings.";
        } else {
          errorMsg.textContent = error.message;
        }
        errorMsg.style.display = 'block';
        btn.textContent = "Log In";
        btn.disabled = false;
      } else {
        window.location.href = "index.html";
      }
    });
    
    // If already logged in, redirect to index
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        window.location.href = "index.html";
      }
    });
  
