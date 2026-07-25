// Temporary UI feature switches. Backend/uploader support remains intact.
export const SHOW_XIAOHONGSHU = false
export const SHOW_BAIJIAHAO = false

export const isPlatformVisible = (platform) => {
  if (platform === '小红书') return SHOW_XIAOHONGSHU
  if (platform === '百家号') return SHOW_BAIJIAHAO
  return true
}
