import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

export function formatChinaTime(value: string): string {
  return `${dayjs.utc(value).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm:ss')}（北京时间）`
}

