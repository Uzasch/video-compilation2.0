/**
 * Share name to drive letter mappings (same as backend)
 */
const SHARE_MAPPINGS = {
  Share: 'S:',
  Share2: 'T:',
  Share3: 'U:',
  Share4: 'V:',
  Share5: 'W:',
  New_Share_1: 'O:',
  New_Share_2: 'P:',
  New_Share_3: 'Q:',
  New_Share_4: 'R:',
}

/**
 * Detect if the client is running on macOS
 */
export function isMac() {
  return navigator.platform.toUpperCase().indexOf('MAC') >= 0
}

/**
 * Detect if the client is running on Windows
 */
export function isWindows() {
  return navigator.platform.toUpperCase().indexOf('WIN') >= 0
}

/**
 * Get the client OS type
 * @returns {'mac' | 'windows' | 'unknown'}
 */
export function getClientOS() {
  if (isMac()) return 'mac'
  if (isWindows()) return 'windows'
  return 'unknown'
}

/**
 * Convert a UNC path to user-friendly format based on client OS
 *
 * @param {string} path - UNC path (e.g., \\192.168.1.6\Share3\Public\video.mp4)
 * @returns {string} User-friendly path
 *
 * @example
 * // On Windows:
 * convertPathForClient("\\\\192.168.1.6\\Share3\\Public\\file.mp4")
 * // Returns: "U:\\Public\\file.mp4"
 *
 * // On Mac:
 * convertPathForClient("\\\\192.168.1.6\\Share3\\Public\\file.mp4")
 * // Returns: "/Volumes/Share3/Public/file.mp4"
 */
export function convertPathForClient(path) {
  if (!path) return path

  const clientOS = getClientOS()

  // Handle UNC paths (\\192.168.1.6\Share3\...)
  if (path.startsWith('\\\\')) {
    // Normalize mixed slashes to backslashes first
    const normalizedPath = path.replace(/\//g, '\\')
    const parts = normalizedPath.split('\\')
    // parts[0] = '', parts[1] = '', parts[2] = '192.168.1.6', parts[3] = 'Share3', ...
    if (parts.length >= 4) {
      const shareName = parts[3] // e.g., "Share3"
      const remaining = parts.slice(4).join('\\') // Everything after share name

      if (clientOS === 'mac') {
        // Convert to macOS format: /Volumes/Share3/path/to/file
        return `/Volumes/${shareName}/${remaining.replace(/\\/g, '/')}`
      } else {
        // Convert to Windows drive letter format
        if (SHARE_MAPPINGS[shareName]) {
          const drive = SHARE_MAPPINGS[shareName]
          return `${drive}\\${remaining}`
        }
        // Unknown share, return as-is
        return path
      }
    }
  }

  // Handle Docker mount paths (/mnt/share3/...)
  if (path.startsWith('/mnt/')) {
    const parts = path.split('/')
    if (parts.length >= 3) {
      const mountName = parts[2] // e.g., "share3"
      const remaining = parts.slice(3).join('/')

      // Find share name from mount name
      const shareName = Object.keys(SHARE_MAPPINGS).find(
        share => share.toLowerCase() === mountName.toLowerCase()
      )

      if (shareName) {
        if (clientOS === 'mac') {
          return `/Volumes/${shareName}/${remaining}`
        } else {
          const drive = SHARE_MAPPINGS[shareName]
          return `${drive}\\${remaining.replace(/\//g, '\\')}`
        }
      }
    }
  }

  // Return as-is if format not recognized
  return path
}
