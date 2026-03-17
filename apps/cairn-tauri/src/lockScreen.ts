/**
 * Lock Screen for Cairn
 *
 * Uses Polkit for authentication - the system's native auth dialog.
 * This is the Linux-native way to authenticate users, supporting:
 * - Password authentication via PAM
 * - Fingerprint readers
 * - Smartcards
 * - Any other PAM-configured auth method
 */
import { login, getSessionUsername, isAuthenticated, validateSession, getSystemUsername } from './kernel';
import { el } from './dom';

export interface LockScreenOptions {
  /** Called after successful login */
  onLogin: (username: string) => void;
  /** If true, shows as re-authentication (session expired) */
  isReauth?: boolean;
  /** Username to authenticate */
  username?: string;
}

/**
 * Show the login/lock screen.
 * When user clicks authenticate, triggers Polkit system dialog.
 *
 * @param root - The root element to render into
 * @param options - Lock screen options
 */
export async function showLockScreen(root: HTMLElement, options: LockScreenOptions): Promise<void> {
  root.innerHTML = '';

  // Get system username if not provided
  let username = options.username;
  if (!username) {
    username = await getSystemUsername() || '';
  }

  const container = el('div');
  container.className = 'lock-screen';
  container.style.cssText = `
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    background: var(--bg-base, #0f1114);
    font-family: system-ui, -apple-system, sans-serif;
    position: relative;
    overflow: hidden;
  `;

  // Background image
  const bgImage = el('div');
  bgImage.style.cssText = `
    position: absolute;
    inset: 0;
    background-image: url('/sonora-sunrise.webp');
    background-size: cover;
    background-position: center;
    opacity: 0.4;
  `;
  container.appendChild(bgImage);

  // Gradient overlay for readability
  const overlay = el('div');
  overlay.style.cssText = `
    position: absolute;
    inset: 0;
    background: linear-gradient(
      180deg,
      var(--gradient-start) 0%,
      var(--gradient-mid) 50%,
      var(--gradient-end) 100%
    );
    opacity: 0.8;
  `;
  container.appendChild(overlay);

  // Content wrapper (above background)
  const content = el('div');
  content.style.cssText = `
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    width: 100%;
    padding: 40px;
  `;

  // Title
  const logoText = el('div');
  logoText.textContent = 'Talking Rock';
  logoText.style.cssText = `
    font-size: 42px;
    font-weight: 700;
    color: var(--text-primary, #e8e4de);
    letter-spacing: -0.5px;
    margin-bottom: 16px;
    text-shadow: 0 2px 20px rgba(0,0,0,0.5);
  `;

  // Mission statement (under the name)
  const mission = el('div');
  mission.textContent = 'Local, open source, zero trust AI. Small models and footprint, outsized impact and trust.';
  mission.style.cssText = `
    font-size: 16px;
    color: var(--text-secondary, rgba(232, 228, 222, 0.7));
    max-width: 460px;
    text-align: center;
    line-height: 1.6;
    margin-bottom: 40px;
    text-shadow: 0 1px 10px rgba(0,0,0,0.5);
    font-style: italic;
  `;

  // Auth card
  const card = el('div');
  card.className = 'lock-card';
  card.style.cssText = `
    background: var(--bg-surface, rgba(15, 17, 20, 0.95));
    border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
    border-radius: 16px;
    padding: 32px 40px;
    width: 340px;
    backdrop-filter: blur(20px);
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    text-align: center;
    margin-bottom: 40px;
  `;

  // User info
  const userIcon = el('div');
  userIcon.textContent = '👤';
  userIcon.style.cssText = `font-size: 40px; margin-bottom: 10px;`;

  const userLabel = el('div');
  userLabel.textContent = username || 'Unknown User';
  userLabel.style.cssText = `
    font-size: 18px;
    font-weight: 500;
    color: var(--text-primary, #e8e4de);
    margin-bottom: 8px;
  `;

  const infoText = el('div');
  infoText.textContent = options.isReauth
    ? 'Your session has expired. Please re-authenticate.'
    : 'Click below to authenticate with your system credentials';
  infoText.style.cssText = `
    font-size: 13px;
    color: var(--text-tertiary, rgba(232, 228, 222, 0.5));
    margin-bottom: 20px;
    line-height: 1.5;
  `;

  // Error message
  const errorMsg = el('div');
  errorMsg.className = 'login-error';
  errorMsg.style.cssText = `
    display: none;
    padding: 10px 12px;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    color: #fca5a5;
    font-size: 13px;
    margin-bottom: 16px;
  `;

  // Authenticate button
  const authBtn = el('button') as HTMLButtonElement;
  authBtn.type = 'button';
  authBtn.textContent = 'Authenticate';
  authBtn.style.cssText = `
    padding: 14px 32px;
    border: none;
    border-radius: 8px;
    background: var(--theme-primary, #d4a856);
    color: white;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    width: 100%;
  `;
  authBtn.addEventListener('mouseenter', () => {
    authBtn.style.opacity = '0.9';
  });
  authBtn.addEventListener('mouseleave', () => {
    authBtn.style.opacity = '1';
  });

  // Loading state
  let isLoading = false;
  const setLoading = (loading: boolean) => {
    isLoading = loading;
    authBtn.disabled = loading;
    authBtn.textContent = loading ? 'Waiting for authentication...' : 'Authenticate';
    authBtn.style.opacity = loading ? '0.6' : '1';
  };

  // Click handler - triggers Polkit auth
  authBtn.addEventListener('click', async () => {
    if (isLoading || !username) return;

    setLoading(true);
    errorMsg.style.display = 'none';

    try {
      // This triggers the Polkit system dialog
      const result = await login(username, null);

      if (result.success) {
        options.onLogin(username);
      } else {
        errorMsg.textContent = result.error || 'Authentication cancelled or failed';
        errorMsg.style.display = 'block';
      }
    } catch (err) {
      errorMsg.textContent = err instanceof Error ? err.message : 'Authentication failed';
      errorMsg.style.display = 'block';
    } finally {
      setLoading(false);
    }
  });

  card.appendChild(userIcon);
  card.appendChild(userLabel);
  card.appendChild(infoText);
  card.appendChild(errorMsg);
  card.appendChild(authBtn);

  // Vision statement (below card)
  const vision = el('div');
  vision.textContent = 'Center your data around you, not a data center.';
  vision.style.cssText = `
    font-size: 18px;
    font-weight: 500;
    color: var(--text-secondary, rgba(232, 228, 222, 0.7));
    max-width: 460px;
    text-align: center;
    line-height: 1.6;
    letter-spacing: 0.3px;
    text-shadow: 0 1px 10px rgba(0,0,0,0.5);
  `;

  // Security note
  const secNote = el('div');
  secNote.style.cssText = `
    margin-top: 20px;
    font-size: 11px;
    color: var(--text-muted, rgba(232, 228, 222, 0.3));
    text-align: center;
    max-width: 280px;
  `;
  secNote.textContent = 'Authentication via Polkit using your system credentials.';

  content.appendChild(logoText);
  content.appendChild(mission);
  content.appendChild(card);
  content.appendChild(vision);
  content.appendChild(secNote);
  container.appendChild(content);

  root.appendChild(container);
}

/**
 * Show lock screen overlay on top of existing content.
 * Used when session expires.
 *
 * @param onUnlock - Called after successful re-authentication
 */
export async function showLockOverlay(onUnlock: () => void): Promise<void> {
  const username = getSessionUsername();
  if (!username) {
    window.location.reload();
    return;
  }

  // Create overlay
  const overlay = el('div');
  overlay.id = 'lock-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000;
    background: var(--bg-surface, rgba(15, 17, 20, 0.95));
    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: system-ui, -apple-system, sans-serif;
  `;

  const card = el('div');
  card.style.cssText = `
    background: var(--modal-bg, #161920);
    border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
    border-radius: 16px;
    padding: 32px;
    width: 300px;
    text-align: center;
  `;

  const lockIcon = el('div');
  lockIcon.textContent = '🔒';
  lockIcon.style.cssText = `font-size: 48px; margin-bottom: 16px;`;

  const title = el('div');
  title.textContent = 'Session Expired';
  title.style.cssText = `
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary, #e8e4de);
    margin-bottom: 8px;
  `;

  const userDisplay = el('div');
  userDisplay.textContent = username;
  userDisplay.style.cssText = `
    font-size: 14px;
    color: var(--text-tertiary, rgba(232, 228, 222, 0.5));
    margin-bottom: 20px;
  `;

  const errorMsg = el('div');
  errorMsg.style.cssText = `
    display: none;
    color: #fca5a5;
    font-size: 13px;
    margin-bottom: 12px;
  `;

  const unlockBtn = el('button') as HTMLButtonElement;
  unlockBtn.textContent = 'Re-authenticate';
  unlockBtn.style.cssText = `
    width: 100%;
    padding: 12px;
    border: none;
    border-radius: 8px;
    background: var(--theme-primary, #d4a856);
    color: white;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  `;

  let isLoading = false;
  const handleUnlock = async () => {
    if (isLoading) return;

    isLoading = true;
    unlockBtn.textContent = 'Waiting for authentication...';
    unlockBtn.disabled = true;
    errorMsg.style.display = 'none';

    try {
      const result = await login(username, null);

      if (result.success) {
        overlay.remove();
        onUnlock();
      } else {
        errorMsg.textContent = result.error || 'Authentication failed';
        errorMsg.style.display = 'block';
      }
    } catch (err) {
      errorMsg.textContent = err instanceof Error ? err.message : 'Authentication failed';
      errorMsg.style.display = 'block';
    } finally {
      isLoading = false;
      unlockBtn.textContent = 'Re-authenticate';
      unlockBtn.disabled = false;
    }
  };

  unlockBtn.addEventListener('click', handleUnlock);

  card.appendChild(lockIcon);
  card.appendChild(title);
  card.appendChild(userDisplay);
  card.appendChild(errorMsg);
  card.appendChild(unlockBtn);
  overlay.appendChild(card);

  document.body.appendChild(overlay);
}

/**
 * Remove lock overlay if present.
 */
export function hideLockOverlay(): void {
  const overlay = document.getElementById('lock-overlay');
  if (overlay) {
    overlay.remove();
  }
}

/**
 * Check session validity and show lock screen if needed.
 * @param onLogin - Called after successful login
 * @returns True if session is valid, false if login is required
 */
export async function checkSessionOrLogin(
  root: HTMLElement,
  onLogin: (username: string) => void
): Promise<boolean> {
  // Check if we have a session token
  if (!isAuthenticated()) {
    await showLockScreen(root, { onLogin });
    return false;
  }

  // Validate the session with the server
  const isValid = await validateSession();
  if (!isValid) {
    const username = getSessionUsername();
    await showLockScreen(root, {
      onLogin,
      isReauth: !!username,
      username: username || undefined,
    });
    return false;
  }

  return true;
}
