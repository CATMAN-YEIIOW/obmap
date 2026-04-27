import { useState, useEffect } from 'react'
import { Table, Button, Modal, Form, Input, Select, InputNumber, message, Tag, Space, Card, Row, Col, Switch, Popconfirm } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { alertApi, buoyApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

const { Option } = Select

interface RuleCondition {
  param: string
  operator: string
  value: number
  logic?: string
}

interface AlertRule {
  id: string
  name: string
  buoy_id: string | null
  buoy_name: string | null
  conditions: RuleCondition[]
  severity: string
  enabled: boolean
  created_by: string | null
  created_at: string
  updated_at: string
}

const paramLabels: Record<string, string> = {
  temperature: '水温',
  salinity: '盐度',
  ph: 'pH值',
  dissolved_oxygen: '溶解氧',
  turbidity: '浊度',
  chlorophyll: '叶绿素',
  wave_height: '波高'
}

const operatorLabels: Record<string, string> = {
  '>': '大于',
  '<': '小于',
  '>=': '大于等于',
  '<=': '小于等于',
  '==': '等于',
  '!=': '不等于'
}

const severityColors: Record<string, string> = {
  info: 'blue',
  warning: 'orange',
  critical: 'red'
}

const AlertRulesPage = () => {
  const [data, setData] = useState<AlertRule[]>([])
  const [buoys, setBuoys] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null)
  const [form] = Form.useForm()
  const [filterBuoy, setFilterBuoy] = useState<string | undefined>()
  const { user } = useAuthStore()

  const canManage = user?.role === 'admin' || user?.role === 'researcher'

  useEffect(() => {
    fetchRules()
    fetchBuoys()
  }, [filterBuoy])

  const fetchRules = async () => {
    setLoading(true)
    try {
      const res = await alertApi.getRules(filterBuoy ? { buoy_id: filterBuoy } : {})
      setData(res.data.data?.items || [])
    } catch (error) {
      message.error('获取规则失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchBuoys = async () => {
    try {
      const res = await buoyApi.list({ page_size: 100 })
      setBuoys(res.data?.items || [])
    } catch (error) {
      console.error('Failed to fetch buoys:', error)
    }
  }

  const handleAdd = () => {
    setEditingRule(null)
    form.resetFields()
    form.setFieldsValue({
      conditions: [{ param: '', operator: '>', value: 0, logic: 'AND' }],
      enabled: true,
      severity: 'warning'
    })
    setModalVisible(true)
  }

  const handleEdit = (record: AlertRule) => {
    setEditingRule(record)
    form.setFieldsValue({
      name: record.name,
      buoy_id: record.buoy_id,
      conditions: record.conditions,
      severity: record.severity,
      enabled: record.enabled
    })
    setModalVisible(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await alertApi.deleteRule(id)
      message.success('删除成功')
      fetchRules()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      // Process conditions - remove logic from last item
      const processedConditions = values.conditions.map((c: RuleCondition, idx: number) => ({
        param: c.param,
        operator: c.operator,
        value: c.value,
        logic: idx < values.conditions.length - 1 ? c.logic : null
      }))

      const payload = {
        ...values,
        conditions: processedConditions
      }

      if (editingRule) {
        await alertApi.updateRule(editingRule.id, payload)
        message.success('更新成功')
      } else {
        await alertApi.createRule(payload)
        message.success('创建成功')
      }
      setModalVisible(false)
      fetchRules()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败')
    }
  }

  const addCondition = () => {
    const conditions = form.getFieldValue('conditions') || []
    form.setFieldValue('conditions', [...conditions, { param: '', operator: '>', value: 0, logic: 'AND' }])
  }

  const removeCondition = (idx: number) => {
    const conditions = form.getFieldValue('conditions') || []
    if (conditions.length > 1) {
      form.setFieldValue('conditions', conditions.filter((_: any, i: number) => i !== idx))
    }
  }

  const renderCondition = (condition: RuleCondition, idx: number, count: number) => (
    <Space key={idx} style={{ display: 'flex', marginBottom: 8 }} align="start">
      {idx > 0 && (
        <Select
          value={condition.logic}
          onChange={(v) => {
            const conditions = form.getFieldValue('conditions')
            conditions[idx].logic = v
            form.setFieldValue('conditions', [...conditions])
          }}
          style={{ width: 80 }}
        >
          <Option value="AND">且</Option>
          <Option value="OR">或</Option>
        </Select>
      )}
      <Select
        value={condition.param}
        onChange={(v) => {
          const conditions = form.getFieldValue('conditions')
          conditions[idx].param = v
          form.setFieldValue('conditions', [...conditions])
        }}
        placeholder="参数"
        style={{ width: 100 }}
      >
        {Object.entries(paramLabels).map(([k, v]) => (
          <Option key={k} value={k}>{v}</Option>
        ))}
      </Select>
      <Select
        value={condition.operator}
        onChange={(v) => {
          const conditions = form.getFieldValue('conditions')
          conditions[idx].operator = v
          form.setFieldValue('conditions', [...conditions])
        }}
        placeholder="运算符"
        style={{ width: 100 }}
      >
        {Object.entries(operatorLabels).map(([k, v]) => (
          <Option key={k} value={k}>{v}</Option>
        ))}
      </Select>
      <InputNumber
        value={condition.value}
        onChange={(v) => {
          const conditions = form.getFieldValue('conditions')
          conditions[idx].value = v
          form.setFieldValue('conditions', [...conditions])
        }}
        placeholder="阈值"
        style={{ width: 100 }}
      />
      {count > 1 && (
        <Button type="text" danger icon={<CloseCircleOutlined />} onClick={() => removeCondition(idx)} />
      )}
    </Space>
  )

  const columns = [
    {
      title: '规则名称',
      dataIndex: 'name',
      key: 'name',
      width: 180
    },
    {
      title: '浮标',
      dataIndex: 'buoy_name',
      key: 'buoy_name',
      render: (name: string | null, record: AlertRule) =>
        record.buoy_id ? (name || record.buoy_id.slice(0, 8) + '...') : '全局',
      width: 120
    },
    {
      title: '条件',
      dataIndex: 'conditions',
      key: 'conditions',
      render: (conditions: RuleCondition[]) => (
        <div>
          {conditions?.map((c, idx) => (
            <span key={idx}>
              {idx > 0 && <Tag color="blue" style={{ margin: '0 4px' }}>{c.logic === 'OR' ? '或' : '且'}</Tag>}
              {paramLabels[c.param] || c.param} {operatorLabels[c.operator]} {c.value}
            </span>
          ))}
        </div>
      ),
      width: 300
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (v: string) => (
        <Tag color={severityColors[v]}>{v === 'info' ? '信息' : v === 'warning' ? '警告' : '严重'}</Tag>
      ),
      width: 100
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'default'}>{enabled ? '启用' : '禁用'}</Tag>
      ),
      width: 80
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      key: 'created_by',
      render: (v: string | null) => v || '-',
      width: 100
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: AlertRule) => (
        <Space>
          {canManage && (
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
              编辑
            </Button>
          )}
          {canManage && (
            <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
      width: 150
    }
  ]

  return (
    <div>
      <Card
        title="组合告警规则"
        extra={
          canManage && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              添加规则
            </Button>
          )
        }
      >
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Select
              allowClear
              placeholder="筛选浮标"
              style={{ width: '100%' }}
              onChange={(v) => setFilterBuoy(v)}
            >
              {buoys.map(b => (
                <Option key={b.id} value={b.id}>{b.name}</Option>
              ))}
            </Select>
          </Col>
        </Row>

        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>

      <Modal
        title={editingRule ? '编辑组合规则' : '添加组合规则'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        okText="确定"
        cancelText="取消"
        width={700}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="规则名称"
            rules={[{ required: true, message: '请输入规则名称' }]}
          >
            <Input placeholder="例如：高温高pH组合告警" />
          </Form.Item>

          <Form.Item
            name="buoy_id"
            label="适用浮标"
          >
            <Select placeholder="选择浮标（不选则为全局规则）" allowClear style={{ width: '100%' }}>
              {buoys.map(b => (
                <Option key={b.id} value={b.id}>{b.name} ({b.code})</Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item label="组合条件">
            <Form.List name="conditions">
              {(fields) => (
                <>
                  {fields.map((field) => (
                    renderCondition(form.getFieldValue('conditions')[field.name], field.name, fields.length)
                  ))}
                  <Button type="dashed" onClick={addCondition} block style={{ marginTop: 8 }}>
                    添加条件
                  </Button>
                </>
              )}
            </Form.List>
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="severity" label="严重程度" initialValue="warning">
                <Select>
                  <Option value="info">信息</Option>
                  <Option value="warning">警告</Option>
                  <Option value="critical">严重</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="enabled" label="启用状态" valuePropName="checked" initialValue={true}>
                <Switch checkedChildren="启用" unCheckedChildren="禁用" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}

export default AlertRulesPage