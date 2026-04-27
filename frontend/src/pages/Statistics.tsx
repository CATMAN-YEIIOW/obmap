import { useState, useEffect } from 'react'
import { Row, Col, Card, Select, DatePicker, Button, Statistic, message, Dropdown, Space, Tag, Modal, Form, Checkbox } from 'antd'
import { DownloadOutlined, DownOutlined, FileTextOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs, { Dayjs } from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import { buoyApi, statisticsApi } from '../services/api'
import { Buoy } from '../stores/appStore'

dayjs.extend(utc)
dayjs.extend(timezone)

const BEIJING_TZ = 'Asia/Shanghai'

const { RangePicker } = DatePicker

const PARAM_CONFIG = [
  { label: '水温 (°C)', value: 'temperature' },
  { label: '盐度 (PSU)', value: 'salinity' },
  { label: 'pH值', value: 'ph' },
  { label: '溶解氧 (mg/L)', value: 'dissolved_oxygen' },
  { label: '浊度 (NTU)', value: 'turbidity' },
  { label: '叶绿素 (μg/L)', value: 'chlorophyll' },
  { label: '波高 (m)', value: 'wave_height' }
]

// 报表类型选项
const REPORT_TYPE_OPTIONS = [
  { label: '日报', value: 'daily' },
  { label: '周报', value: 'weekly' },
  { label: '月报', value: 'monthly' },
  { label: '季报', value: 'quarterly' }
]

// 视图模式：raw=原始数据，aggregated=聚合数据
const VIEW_OPTIONS = [
  { label: '近7天（原始数据）', value: 'day', bucket: 'raw' },
  { label: '近4周（日级聚合）', value: 'week', bucket: '1d' },
  { label: '近3个月（日级聚合）', value: 'month', bucket: '1d' }
]

interface ThresholdConfig {
  min_threshold: number | null
  max_threshold: number | null
  severity: string
}

interface AlertEvent {
  id: string
  param_name: string
  alert_type: string
  severity: string
  actual_value: number
  threshold_value: number
  triggered_at: string
}

const Statistics = () => {
  const [buoys, setBuoys] = useState<Buoy[]>([])
  const [selectedBuoy, setSelectedBuoy] = useState<string>('')
  const [param, setParam] = useState<string>('temperature')
  const [period, setPeriod] = useState<'day' | 'week' | 'month'>('day')
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().tz(BEIJING_TZ).subtract(7, 'day'),
    dayjs().tz(BEIJING_TZ)
  ])
  const [chartData, setChartData] = useState<any>({})
  const [summary, setSummary] = useState<any>(null)
  const [thresholds, setThresholds] = useState<Record<string, ThresholdConfig>>({})
  const [alertEvents, setAlertEvents] = useState<AlertEvent[]>([])
  const [exportLoading, setExportLoading] = useState(false)

  // 报表导出相关状态
  const [reportModalVisible, setReportModalVisible] = useState(false)
  const [reportBuoyIds, setReportBuoyIds] = useState<string[]>([])
  const [reportType, setReportType] = useState<'daily' | 'weekly' | 'monthly' | 'quarterly'>('daily')
  const [customTimeRange, setCustomTimeRange] = useState<boolean>(false)
  const [reportTimeRange, setReportTimeRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [reportLoading, setReportLoading] = useState(false)

  // Fetch buoys on mount
  useEffect(() => {
    fetchBuoys()
  }, [])

  // Fetch statistics when filters change
  useEffect(() => {
    if (selectedBuoy && dateRange) {
      fetchStatistics()
      fetchThresholds()
      fetchAlertEvents()
    }
  }, [selectedBuoy, param, dateRange, period])

  const fetchBuoys = async () => {
    try {
      const res = await buoyApi.list({ page_size: 100 })
      setBuoys(res.data.items)
      if (res.data.items && res.data.items.length > 0) {
        setSelectedBuoy(res.data.items[0].id)
      }
    } catch (error) {
      console.error('Failed to fetch buoys:', error)
    }
  }

  const fetchThresholds = async () => {
    if (!selectedBuoy) return
    try {
      const res = await statisticsApi.thresholds({ buoy_id: selectedBuoy })
      setThresholds(res.data?.data?.thresholds || {})
    } catch (error) {
      console.error('Failed to fetch thresholds:', error)
    }
  }

  const fetchAlertEvents = async () => {
    if (!selectedBuoy || !dateRange) return
    try {
      const [startTime, endTime] = dateRange
      const startStr = startTime.utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
      const endStr = endTime.utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
      const res = await statisticsApi.alertEvents({
        buoy_id: selectedBuoy,
        start_time: startStr,
        end_time: endStr
      })
      setAlertEvents(res.data?.data?.items || [])
    } catch (error) {
      console.error('Failed to fetch alert events:', error)
    }
  }

  const fetchStatistics = async () => {
    if (!selectedBuoy || !dateRange) return

    try {
      const [startTime, endTime] = dateRange
      const startStr = startTime.utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
      const endStr = endTime.utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')

      // Fetch summary
      const summaryRes = await statisticsApi.summary({
        buoy_id: selectedBuoy,
        start_time: startStr,
        end_time: endStr
      })
      setSummary(summaryRes.data?.data)

      const viewOption = VIEW_OPTIONS.find(v => v.value === period)
      const isRaw = viewOption?.bucket === 'raw'

      if (isRaw) {
        // 原始数据视图（近7天）
        const rawRes = await statisticsApi.raw({
          buoy_id: selectedBuoy,
          param,
          start_time: startStr,
          end_time: endStr
        })
        const items = rawRes.data?.data?.items
        if (items && items.length > 0) {
          setChartData({
            time: items.map((item: any) => dayjs.utc(item.time).tz(BEIJING_TZ).format('YYYY-MM-DD HH:mm')),
            values: items.map((item: any) => item.value),
            type: 'raw'
          })
        } else {
          setChartData({})
        }
      } else {
        // 聚合数据视图（周/月）
        const timeseriesRes = await statisticsApi.timeseries({
          buoy_id: selectedBuoy,
          param,
          start_time: startStr,
          end_time: endStr,
          bucket: viewOption?.bucket || '1d'
        })

        const items = timeseriesRes.data?.data?.items
        if (items && items.length > 0) {
          setChartData({
            time: items.map((item: any) => dayjs.utc(item.time).tz(BEIJING_TZ).format('YYYY-MM-DD HH:mm')),
            avg: items.map((item: any) => item.avg),
            min: items.map((item: any) => item.min),
            max: items.map((item: any) => item.max),
            type: 'aggregated'
          })
        } else {
          setChartData({})
        }
      }
    } catch (error) {
      console.error('Failed to fetch statistics:', error)
    }
  }

  const handleExport = async (format: 'csv' | 'xlsx') => {
    if (!selectedBuoy || !dateRange) {
      message.warning('请先选择浮标和时间范围')
      return
    }

    setExportLoading(true)
    try {
      const [startTime, endTime] = dateRange
      const startStr = startTime.utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
      const endStr = endTime.utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
      const res = await statisticsApi.exportData({
        buoy_id: selectedBuoy,
        start_time: startStr,
        end_time: endStr,
        format
      })

      if (format === 'xlsx') {
        const blob = new Blob([res.data as unknown as BlobPart], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        const buoy = buoys.find(b => b.id === selectedBuoy)
        link.href = url
        link.download = `buoy_data_${buoy?.code || selectedBuoy}_${startTime.tz(BEIJING_TZ).format('YYYYMMDD')}_${endTime.tz(BEIJING_TZ).format('YYYYMMDD')}.xlsx`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        message.success('Excel 导出成功')
      } else {
        // CSV 导出
        const blob = new Blob([res.data as unknown as BlobPart], {
          type: 'text/csv;charset=utf-8'
        })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        const buoy = buoys.find(b => b.id === selectedBuoy)
        link.href = url
        link.download = `buoy_data_${buoy?.code || selectedBuoy}_${startTime.tz(BEIJING_TZ).format('YYYYMMDD')}_${endTime.tz(BEIJING_TZ).format('YYYYMMDD')}.csv`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        message.success('CSV 导出成功')
      }
    } catch (error) {
      console.error('Export failed:', error)
      message.error('导出失败')
    } finally {
      setExportLoading(false)
    }
  }

  // 生成报表
  const handleGenerateReport = async () => {
    if (reportBuoyIds.length === 0) {
      message.warning('请至少选择一个浮标')
      return
    }

    if (customTimeRange && !reportTimeRange) {
      message.warning('请选择自定义时间范围')
      return
    }

    setReportLoading(true)
    try {
      let startTimeStr: string | undefined
      let endTimeStr: string | undefined

      if (customTimeRange && reportTimeRange) {
        startTimeStr = reportTimeRange[0].utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
        endTimeStr = reportTimeRange[1].utcOffset(0).format('YYYY-MM-DDTHH:mm:ss[Z]')
      }

      const res = await statisticsApi.generateReport({
        buoy_ids: reportBuoyIds,
        report_type: reportType,
        start_time: startTimeStr,
        end_time: endTimeStr,
        include_trends: true
      })

      // 下载 PDF
      const blob = new Blob([res.data as unknown as BlobPart], {
        type: 'application/pdf'
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const buoyNames = reportBuoyIds.length <= 2
        ? reportBuoyIds.map(id => buoys.find(b => b.id === id)?.code || id.slice(0, 8)).join('_')
        : `${buoys.find(b => b.id === reportBuoyIds[0])?.code || reportBuoyIds[0]}_etc`
      const typeNames = { daily: '日报', weekly: '周报', monthly: '月报', quarterly: '季报' }
      const dateStr = dayjs().tz(BEIJING_TZ).format('YYYYMMDD')
      link.href = url
      link.download = `OBMAP_${typeNames[reportType]}_${buoyNames}_${dateStr}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      message.success('报表生成成功')
      setReportModalVisible(false)
    } catch (error) {
      console.error('Report generation failed:', error)
      message.error('报表生成失败')
    } finally {
      setReportLoading(false)
    }
  }

  const paramLabel = PARAM_CONFIG.find(p => p.value === param)?.label || param
  const currentThreshold = thresholds[param]

  // 构建阈值标注线
  const getMarkLines = () => {
    const lines: any[] = []

    if (currentThreshold) {
      const thresholdColor = currentThreshold.severity === 'critical' ? '#f5222d' : '#fa8c16'
      if (currentThreshold.max_threshold !== null) {
        lines.push({
          name: '上限阈值',
          yAxis: currentThreshold.max_threshold,
          lineStyle: { color: thresholdColor, type: 'dashed', width: 2 },
          label: { show: true, formatter: `上限: ${currentThreshold.max_threshold}`, position: 'end' }
        })
      }
      if (currentThreshold.min_threshold !== null) {
        lines.push({
          name: '下限阈值',
          yAxis: currentThreshold.min_threshold,
          lineStyle: { color: '#52c41a', type: 'dashed', width: 2 },
          label: { show: true, formatter: `下限: ${currentThreshold.min_threshold}`, position: 'end' }
        })
      }
    }

    return lines
  }

  const getChartOption = () => {
    const isRaw = chartData.type === 'raw'
    const markLines = getMarkLines()

    const baseOption = {
      title: { text: `${paramLabel} 统计分析`, left: 'center' },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          let result = `<b>${params[0].name}</b><br/>`
          params.forEach((p: any) => {
            if (p.value !== null && p.value !== undefined && p.seriesName !== '阈值线') {
              result += `${p.marker} ${p.seriesName}: <b>${p.value}</b><br/>`
            }
          })
          // 显示告警信息
          const paramAlerts = alertEvents.filter(e => e.param_name === param)
          const alertAtTime = paramAlerts.find(a =>
            dayjs.utc(a.triggered_at).tz(BEIJING_TZ).format('YYYY-MM-DD HH:mm') === params[0].name
          )
          if (alertAtTime) {
            result += `<span style="color:#f5222d">⚠️ 触发告警: ${alertAtTime.actual_value} (阈值: ${alertAtTime.threshold_value})</span>`
          }
          return result
        }
      },
      legend: {
        data: isRaw ? [paramLabel] : ['平均值', '最大值', '最小值'],
        top: 30
      },
      grid: { top: isRaw ? 70 : 80, left: 50, right: 30, bottom: 50 },
      xAxis: {
        type: 'category',
        data: chartData.time || [],
        axisLabel: { rotate: 30 }
      },
      yAxis: { type: 'value' },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', start: 0, end: 100 }
      ]
    }

    // 构建 markLine 配置
    const markLineConfig = markLines.length > 0 ? {
      symbol: ['none', 'none'],
      lineStyle: { width: 2 },
      label: { show: true, position: 'end' },
      data: markLines.filter(l => l.yAxis !== undefined)
    } : undefined

    if (isRaw) {
      // 原始数据视图：显示单条线，超限高亮
      const values = chartData.values || []
      const threshold = currentThreshold

      // 为每个数据点设置颜色：超过阈值的用红色/橙色
      const coloredData = values.map((v: number) => {
        let color = '#1890ff'
        if (threshold) {
          if (threshold.max_threshold !== null && v > threshold.max_threshold) {
            color = threshold.severity === 'critical' ? '#f5222d' : '#fa8c16'
          } else if (threshold.min_threshold !== null && v < threshold.min_threshold) {
            color = threshold.severity === 'critical' ? '#f5222d' : '#fa8c16'
          }
        }
        return {
          value: v,
          itemStyle: { color }
        }
      })

      return {
        ...baseOption,
        series: [{
          name: paramLabel,
          type: 'line',
          data: coloredData,
          smooth: false,
          lineStyle: { width: 1.5 },
          itemStyle: { color: '#1890ff' },
          markLine: markLineConfig
        }]
      }
    } else {
      // 聚合数据视图：显示avg/min/max三条线
      return {
        ...baseOption,
        series: [
          {
            name: '平均值',
            type: 'line',
            data: chartData.avg || [],
            smooth: true,
            lineStyle: { width: 2 },
            itemStyle: { color: '#1890ff' },
            markLine: markLineConfig
          },
          {
            name: '最大值',
            type: 'line',
            data: chartData.max || [],
            smooth: true,
            lineStyle: { width: 1, type: 'dashed' },
            itemStyle: { color: '#f5222d' }
          },
          {
            name: '最小值',
            type: 'line',
            data: chartData.min || [],
            smooth: true,
            lineStyle: { width: 1, type: 'dashed' },
            itemStyle: { color: '#52c41a' }
          }
        ]
      }
    }
  }

  // 计算超标统计
  const getOverLimitStats = () => {
    if (!currentThreshold || !chartData.values) return null

    const values = chartData.values
    let overMaxCount = 0
    let underMinCount = 0
    let maxOverLimit = 0

    values.forEach((v: number) => {
      if (currentThreshold.max_threshold !== null && v > currentThreshold.max_threshold) {
        overMaxCount++
        maxOverLimit = Math.max(maxOverLimit, v - (currentThreshold.max_threshold || 0))
      }
      if (currentThreshold.min_threshold !== null && v < currentThreshold.min_threshold) {
        underMinCount++
        maxOverLimit = Math.max(maxOverLimit, (currentThreshold.min_threshold || 0) - v)
      }
    })

    const total = values.length
    const overLimitPercent = ((overMaxCount + underMinCount) / total * 100).toFixed(1)

    return {
      overMaxCount,
      underMinCount,
      total,
      overLimitPercent,
      maxOverLimit: maxOverLimit.toFixed(2)
    }
  }

  const overLimitStats = getOverLimitStats()

  return (
    <div>
      {/* 控制栏 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={5}>
          <Card size="small">
            <Select
              value={selectedBuoy}
              onChange={setSelectedBuoy}
              placeholder="选择浮标"
              style={{ width: '100%' }}
              options={buoys.map(b => ({ label: `${b.name} (${b.code})`, value: b.id }))}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Select
              value={param}
              onChange={setParam}
              options={PARAM_CONFIG}
              style={{ width: '100%' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Select
              value={period}
              onChange={v => setPeriod(v)}
              options={VIEW_OPTIONS}
              style={{ width: '100%' }}
            />
          </Card>
        </Col>
        <Col span={7}>
          <Card size="small">
            <RangePicker
              value={dateRange}
              onChange={(dates: any) => dates && setDateRange(dates)}
              showTime
              style={{ width: '100%' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Space>
              <Dropdown
                menu={{
                  items: [
                    { key: 'xlsx', label: '导出 Excel', onClick: () => handleExport('xlsx') },
                    { key: 'csv', label: '导出 CSV', onClick: () => handleExport('csv') }
                  ]
                }}
              >
                <Button icon={<DownloadOutlined />} loading={exportLoading}>
                  导出数据 <DownOutlined />
                </Button>
              </Dropdown>
              <Button
                icon={<FileTextOutlined />}
                onClick={() => {
                  setReportBuoyIds(selectedBuoy ? [selectedBuoy] : [])
                  setReportModalVisible(true)
                }}
              >
                生成报表
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 阈值信息 */}
      {currentThreshold && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>阈值配置</div>
              <div>
                {currentThreshold.min_threshold !== null && (
                  <Tag color="blue">下限: {currentThreshold.min_threshold}</Tag>
                )}
                {currentThreshold.max_threshold !== null && (
                  <Tag color={currentThreshold.severity === 'critical' ? 'red' : 'orange'}>
                    上限: {currentThreshold.max_threshold}
                  </Tag>
                )}
                {currentThreshold.min_threshold === null && currentThreshold.max_threshold === null && (
                  <span style={{ color: '#999' }}>无配置</span>
                )}
              </div>
            </Card>
          </Col>
          {overLimitStats && (
            <>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="超标点数"
                    value={overLimitStats.overMaxCount + overLimitStats.underMinCount}
                    suffix={`/ ${overLimitStats.total}`}
                    valueStyle={{ color: (overLimitStats.overMaxCount + overLimitStats.underMinCount) > 0 ? '#f5222d' : '#52c41a' }}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="超标比例"
                    value={overLimitStats.overLimitPercent}
                    suffix="%"
                    valueStyle={{ color: parseFloat(overLimitStats.overLimitPercent) > 0 ? '#f5222d' : '#52c41a' }}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="最大超限幅度"
                    value={overLimitStats.maxOverLimit}
                    suffix={PARAM_CONFIG.find(p => p.value === param)?.label.split(' ')[1] || ''}
                    valueStyle={{ color: parseFloat(overLimitStats.maxOverLimit) > 0 ? '#f5222d' : '#52c41a' }}
                  />
                </Card>
              </Col>
            </>
          )}
          <Col span={6}>
            <Card size="small">
              <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>告警事件</div>
              <div>
                {alertEvents.length > 0 ? (
                  <Tag color="red">{alertEvents.length} 次告警</Tag>
                ) : (
                  <span style={{ color: '#52c41a' }}>无告警</span>
                )}
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* 统计卡片 */}
      {summary && summary.statistics && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="记录数" value={summary.records || 0} />
            </Card>
          </Col>
          {summary.statistics[param] ? (
            <>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="最小值"
                    value={summary.statistics[param].min}
                    suffix={summary.statistics[param].unit || ''}
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="平均值"
                    value={summary.statistics[param].avg}
                    suffix={summary.statistics[param].unit || ''}
                    valueStyle={{ color: '#1890ff' }}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="最大值"
                    value={summary.statistics[param].max}
                    suffix={summary.statistics[param].unit || ''}
                    valueStyle={{ color: '#f5222d' }}
                  />
                </Card>
              </Col>
              <Col span={4}>
                <Card size="small">
                  <Statistic
                    title="标准差"
                    value={summary.statistics[param].std || '-'}
                    suffix={summary.statistics[param].unit || ''}
                  />
                </Card>
              </Col>
            </>
          ) : (
            <Col span={16}>
              <Card size="small">
                <div style={{ color: '#999' }}>该时间段内暂无 {paramLabel} 数据</div>
              </Card>
            </Col>
          )}
        </Row>
      )}

      {/* 趋势图 */}
      <Row gutter={16}>
        <Col span={24}>
          <Card
            title="时序统计"
            extra={
              <Space>
                {currentThreshold && (
                  <Space size={4}>
                    <span style={{ color: '#999', fontSize: 12 }}>阈值:</span>
                    {currentThreshold.min_threshold !== null && (
                      <span style={{ color: '#52c41a', fontSize: 12 }}>下限{currentThreshold.min_threshold}</span>
                    )}
                    {currentThreshold.max_threshold !== null && (
                      <span style={{ color: currentThreshold.severity === '#f5222d' ? '#f5222d' : '#fa8c16', fontSize: 12 }}>
                        上限{currentThreshold.max_threshold}
                      </span>
                    )}
                  </Space>
                )}
                <span style={{ color: '#999', fontSize: 12 }}>可拖动缩放</span>
              </Space>
            }
          >
            <ReactECharts
              option={getChartOption()}
              style={{ height: 450 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 告警事件列表 */}
      {alertEvents.length > 0 && (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card size="small" title="告警事件详情">
              <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                {alertEvents.map(event => (
                  <div key={event.id} style={{ padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                    <Tag color={event.severity === 'critical' ? 'red' : 'orange'}>
                      {event.severity === 'critical' ? '严重' : '警告'}
                    </Tag>
                    <span style={{ marginLeft: 8 }}>
                      {dayjs.utc(event.triggered_at).tz(BEIJING_TZ).format('YYYY-MM-DD HH:mm:ss')}
                    </span>
                    <span style={{ marginLeft: 8 }}>
                      {PARAM_CONFIG.find(p => p.value === event.param_name)?.label || event.param_name}:
                    </span>
                    <span style={{ color: '#f5222d', fontWeight: 'bold', marginLeft: 4 }}>
                      {event.actual_value}
                    </span>
                    <span style={{ color: '#999', marginLeft: 4 }}>
                      (阈值: {event.threshold_value})
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* 报表生成 Modal */}
      <Modal
        title="生成统计报表"
        open={reportModalVisible}
        onCancel={() => setReportModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setReportModalVisible(false)}>
            取消
          </Button>,
          <Button
            key="generate"
            type="primary"
            loading={reportLoading}
            onClick={handleGenerateReport}
          >
            生成 PDF 报表
          </Button>
        ]}
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="报表类型" required>
            <Select
              value={reportType}
              onChange={setReportType}
              options={REPORT_TYPE_OPTIONS}
            />
          </Form.Item>

          <Form.Item label="选择浮标" required>
            <Select
              mode="multiple"
              value={reportBuoyIds}
              onChange={setReportBuoyIds}
              placeholder="请选择浮标（可多选）"
              style={{ width: '100%' }}
              options={buoys.map(b => ({ label: `${b.name} (${b.code})`, value: b.id }))}
            />
          </Form.Item>

          <Form.Item label="时间范围">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Checkbox
                checked={customTimeRange}
                onChange={(e) => {
                  setCustomTimeRange(e.target.checked)
                  if (!e.target.checked) {
                    setReportTimeRange(null)
                  }
                }}
              >
                使用自定义时间范围
              </Checkbox>
              {customTimeRange && (
                <RangePicker
                  value={reportTimeRange}
                  onChange={(dates: any) => setReportTimeRange(dates)}
                  showTime
                  style={{ width: '100%' }}
                  placeholder={['开始时间', '结束时间']}
                />
              )}
              {!customTimeRange && (
                <div style={{ color: '#999', fontSize: 12 }}>
                  将根据报表类型自动计算时间范围：
                  <br />
                  日报 = 今日 | 周报 = 本周一至周日 | 月报 = 本月 | 季报 = 本季度
                </div>
              )}
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Statistics
