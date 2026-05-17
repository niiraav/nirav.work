// ─── Supabase early-access signup (shared by both forms) ───────
const SUPABASE_URL = 'https://vwanxorcmyzfxumhyvxl.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ3YW54b3JjbXl6Znh1bWh5dnhsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxODg3NzksImV4cCI6MjA5Mzc2NDc3OX0.tAkwQCAnky4wG8ihxD_PViStyGpPKNg74-1ry_L7Drc';

const supabaseClient = window.supabase
  ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

function wireSignupForm(formId, inputId, msgId) {
  const form = document.getElementById(formId);
  if (!form) return;
  const input = document.getElementById(inputId);
  const msgEl = document.getElementById(msgId);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = (input.value || '').trim();
    const btn = form.querySelector('button');

    if (!email) return;

    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = 'Joining…';
    msgEl.textContent = '';
    msgEl.className = 'form-message';

    try {
      if (!supabaseClient) throw new Error('Supabase not loaded');

      const { error } = await supabaseClient
        .from('early_access_signups')
        .insert([{ email, source: 'landing_page', trade_type: null }]);

      if (error) {
        if (error.code === '23505') {
          msgEl.textContent = "You're already on the list — we'll be in touch.";
          msgEl.className = 'form-message success';
        } else {
          throw error;
        }
      } else {
        msgEl.textContent = "You're on the list. We'll be in touch soon.";
        msgEl.className = 'form-message success';
        input.value = '';
      }
    } catch (err) {
      console.error(err);
      msgEl.textContent = 'Something went wrong. Please try again.';
      msgEl.className = 'form-message error';
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });
}

wireSignupForm('signup-form',   'email-input',   'form-message');
wireSignupForm('signup-form-2', 'email-input-2', 'form-message-2');

// ─── Pill-group tabs (Cal signature): highlight active step ────
const pillTabs = document.querySelectorAll('.pill-tab');
const stepCards = document.querySelectorAll('.step-card');

pillTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const step = tab.dataset.step;
    pillTabs.forEach(t => {
      const on = t === tab;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    stepCards.forEach(card => {
      const match = card.dataset.step === step;
      card.style.transition = 'transform .35s ease, box-shadow .35s ease, border-color .35s ease';
      card.style.transform = match ? 'translateY(-4px)' : 'translateY(0)';
      card.style.boxShadow = match
        ? '0 22px 40px -22px rgba(17,17,17,0.28)'
        : '';
      card.style.borderColor = match ? '#111111' : '';
    });
  });
});
