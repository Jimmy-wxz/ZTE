/**
 * Agent 评估仪表盘组件
 *
 * 用于展示和比较 WriteHERE 和 Mo-Shen 两个 Agent 的评估结果
 */

import React, { useState, useEffect } from 'react';

// 样式常量
const styles = {
  container: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '20px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  },
  header: {
    textAlign: 'center',
    marginBottom: '30px',
    padding: '20px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    borderRadius: '10px'
  },
  title: {
    fontSize: '2.5rem',
    margin: '0 0 10px 0',
    fontWeight: '600'
  },
  subtitle: {
    fontSize: '1.1rem',
    opacity: 0.9,
    margin: 0
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '20px',
    marginBottom: '30px'
  },
  card: {
    background: 'white',
    borderRadius: '10px',
    padding: '20px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    transition: 'transform 0.2s, box-shadow 0.2s'
  },
  cardHover: {
    transform: 'translateY(-2px)',
    boxShadow: '0 4px 16px rgba(0,0,0,0.15)'
  },
  cardTitle: {
    fontSize: '1.3rem',
    fontWeight: '600',
    marginBottom: '15px',
    color: '#333',
    borderBottom: '2px solid #667eea',
    paddingBottom: '10px'
  },
  metricRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 0',
    borderBottom: '1px solid #eee'
  },
  metricLabel: {
    fontSize: '0.95rem',
    color: '#666'
  },
  metricValue: {
    fontSize: '1.2rem',
    fontWeight: '600'
  },
  scoreGood: {
    color: '#10b981'
  },
  scoreMedium: {
    color: '#f59e0b'
  },
  scoreBad: {
    color: '#ef4444'
  },
  progressBar: {
    width: '100%',
    height: '8px',
    background: '#e5e7eb',
    borderRadius: '4px',
    overflow: 'hidden',
    marginTop: '5px'
  },
  progressFill: (percentage, color) => ({
    height: '100%',
    width: `${percentage}%`,
    background: color,
    transition: 'width 0.5s ease-in-out'
  }),
  button: {
    padding: '12px 24px',
    fontSize: '1rem',
    fontWeight: '500',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    margin: '5px'
  },
  primaryButton: {
    background: '#667eea',
    color: 'white'
  },
  secondaryButton: {
    background: '#e5e7eb',
    color: '#374151'
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    marginTop: '15px'
  },
  th: {
    textAlign: 'left',
    padding: '12px',
    background: '#f9fafb',
    fontWeight: '600',
    color: '#374151',
    borderBottom: '2px solid #e5e7eb'
  },
  td: {
    padding: '12px',
    borderBottom: '1px solid #e5e7eb',
    color: '#1f2937'
  },
  badge: {
    display: 'inline-block',
    padding: '4px 12px',
    borderRadius: '12px',
    fontSize: '0.85rem',
    fontWeight: '500'
  },
  badgeSuccess: {
    background: '#d1fae5',
    color: '#065f46'
  },
  badgeWarning: {
    background: '#fef3c7',
    color: '#92400e'
  },
  badgeError: {
    background: '#fee2e2',
    color: '#991b1b'
  },
  section: {
    marginBottom: '30px'
  },
  comparisonChart: {
    background: 'white',
    borderRadius: '10px',
    padding: '20px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
  }
};

/**
 * 获取分数对应的颜色
 */
const getScoreColor = (score) => {
  if (score >= 80) return '#10b981';
  if (score >= 60) return '#f59e0b';
  return '#ef4444';
};

/**
 * 获取分数对应的样式类
 */
const getScoreClass = (score) => {
  if (score >= 80) return styles.scoreGood;
  if (score >= 60) return styles.scoreMedium;
  return styles.scoreBad;
};

/**
 * 进度条组件
 */
const ProgressBar = ({ percentage, color }) => (
  <div style={styles.progressBar}>
    <div style={styles.progressFill(percentage, color)} />
  </div>
);

/**
 * 指标行组件
 */
const MetricRow = ({ label, value, showProgress = false, suffix = '' }) => {
  const color = getScoreColor(value);

  return (
    <div style={styles.metricRow}>
      <span style={styles.metricLabel}>{label}</span>
      <div style={{ flex: 1, marginLeft: '20px' }}>
        <div style={{ ...styles.metricValue, ...getScoreClass(value), textAlign: 'right' }}>
          {value.toFixed(1)}{suffix}
        </div>
        {showProgress && <ProgressBar percentage={value} color={color} />}
      </div>
    </div>
  );
};

/**
 * Agent 卡片组件
 */
const AgentCard = ({ agentType, evaluation, onClick }) => {
  const [isHovered, setIsHovered] = useState(false);

  if (!evaluation) {
    return (
      <div style={styles.card}>
        <h3 style={styles.cardTitle}>
          {agentType === 'writehere' ? 'WriteHERE' : 'Mo-Shen'}
        </h3>
        <p style={{ color: '#9ca3af' }}>暂无评估数据</p>
      </div>
    );
  }

  return (
    <div
      style={{
        ...styles.card,
        ...(isHovered ? styles.cardHover : {})
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
    >
      <h3 style={styles.cardTitle}>
        {agentType === 'writehere' ? '📝 WriteHERE' : '🖋️ Mo-Shen'}
      </h3>

      <MetricRow
        label="单步级别综合得分"
        value={evaluation.overall_step_level_score}
        showProgress={true}
        suffix="/100"
      />

      <MetricRow
        label="轨迹级别综合得分"
        value={evaluation.overall_trajectory_level_score}
        showProgress={true}
        suffix="/100"
      />

      <div style={{ marginTop: '15px', paddingTop: '15px', borderTop: '2px solid #f3f4f6' }}>
        <div style={styles.metricRow}>
          <span style={styles.metricLabel}>LLM 调用准确率</span>
          <span style={{ ...styles.metricValue, ...getScoreClass(evaluation.llm_call_accuracy) }}>
            {evaluation.llm_call_accuracy.toFixed(1)}%
          </span>
        </div>

        <div style={styles.metricRow}>
          <span style={styles.metricLabel}>工具调用准确率</span>
          <span style={{ ...styles.metricValue, ...getScoreClass(evaluation.tool_call_accuracy) }}>
            {evaluation.tool_call_accuracy.toFixed(1)}%
          </span>
        </div>

        <div style={styles.metricRow}>
          <span style={styles.metricLabel}>轨迹成功率</span>
          <span style={{ ...styles.metricValue, ...getScoreClass(evaluation.trajectory_success_rate) }}>
            {evaluation.trajectory_success_rate.toFixed(1)}%
          </span>
        </div>

        <div style={styles.metricRow}>
          <span style={styles.metricLabel}>平均耗时</span>
          <span style={styles.metricValue}>
            {(evaluation.avg_trajectory_duration_ms / 1000).toFixed(1)}秒
          </span>
        </div>
      </div>
    </div>
  );
};

/**
 * 详细对比表格组件
 */
const ComparisonTable = ({ writehereEval, moShenEval }) => {
  const metrics = [
    { key: 'overall_step_level_score', label: '单步级别综合得分', suffix: '/100' },
    { key: 'overall_trajectory_level_score', label: '轨迹级别综合得分', suffix: '/100' },
    { key: 'llm_call_accuracy', label: 'LLM 调用准确率', suffix: '%' },
    { key: 'tool_call_accuracy', label: '工具调用准确率', suffix: '%' },
    { key: 'parameter_format_accuracy', label: '参数格式准确率', suffix: '%' },
    { key: 'response_parse_accuracy', label: '响应解析准确率', suffix: '%' },
    { key: 'avg_rationality_score', label: '平均合理性得分', suffix: '/100' },
    { key: 'avg_efficiency_score', label: '平均效率得分', suffix: '/100' },
    { key: 'trajectory_success_rate', label: '轨迹成功率', suffix: '%' },
    { key: 'avg_trajectory_duration_ms', label: '平均轨迹耗时', suffix: 'ms', lowerIsBetter: true }
  ];

  return (
    <div style={styles.card}>
      <h3 style={styles.cardTitle}>详细对比</h3>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>指标</th>
            <th style={styles.th}>WriteHERE</th>
            <th style={styles.th}>Mo-Shen</th>
            <th style={styles.th}>差异</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map(({ key, label, suffix, lowerIsBetter }) => {
            const writehereValue = writehereEval?.[key] || 0;
            const moShenValue = moShenEval?.[key] || 0;
            const diff = writehereValue - moShenValue;

            let diffDisplay;
            if (diff === 0) {
              diffDisplay = '=';
            } else if ((diff > 0 && !lowerIsBetter) || (diff < 0 && lowerIsBetter)) {
              diffDisplay = `+${Math.abs(diff).toFixed(1)}`;
            } else {
              diffDisplay = `-${Math.abs(diff).toFixed(1)}`;
            }

            const betterAgent = writehereValue > moShenValue ? 'writehere' :
                               moShenValue > writehereValue ? 'mo_shen' : null;

            return (
              <tr key={key}>
                <td style={styles.td}>{label}</td>
                <td style={{
                  ...styles.td,
                  fontWeight: betterAgent === 'writehere' ? '600' : 'normal',
                  color: betterAgent === 'writehere' ? '#10b981' : 'inherit'
                }}>
                  {writehereValue.toFixed(1)}{suffix}
                </td>
                <td style={{
                  ...styles.td,
                  fontWeight: betterAgent === 'mo_shen' ? '600' : 'normal',
                  color: betterAgent === 'mo_shen' ? '#10b981' : 'inherit'
                }}>
                  {moShenValue.toFixed(1)}{suffix}
                </td>
                <td style={{
                  ...styles.td,
                  color: diff > 0 && !lowerIsBetter ? '#10b981' :
                         diff < 0 && !lowerIsBetter ? '#ef4444' :
                         diff > 0 && lowerIsBetter ? '#ef4444' :
                         diff < 0 && lowerIsBetter ? '#10b981' : '#6b7280'
                }}>
                  {diffDisplay}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

/**
 * 问题与建议组件
 */
const IssuesAndSuggestions = ({ evaluation, agentType }) => {
  if (!evaluation || (!evaluation.identified_issues?.length && !evaluation.improvement_suggestions?.length)) {
    return null;
  }

  return (
    <div style={styles.card}>
      <h3 style={styles.cardTitle}>
        {agentType === 'writehere' ? 'WriteHERE' : 'Mo-Shen'} - 问题与建议
      </h3>

      {evaluation.identified_issues?.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '1.1rem', color: '#ef4444', marginBottom: '10px' }}>
            ⚠️ 已识别的问题
          </h4>
          <ul style={{ paddingLeft: '20px', color: '#4b5563' }}>
            {evaluation.identified_issues.map((issue, index) => (
              <li key={index} style={{ marginBottom: '8px' }}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      {evaluation.improvement_suggestions?.length > 0 && (
        <div>
          <h4 style={{ fontSize: '1.1rem', color: '#10b981', marginBottom: '10px' }}>
            💡 改进建议
          </h4>
          <ul style={{ paddingLeft: '20px', color: '#4b5563' }}>
            {evaluation.improvement_suggestions.map((suggestion, index) => (
              <li key={index} style={{ marginBottom: '8px' }}>{suggestion}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

/**
 * 轨迹详情组件
 */
const TrajectoryDetails = ({ trajectory }) => {
  const getStatusBadge = (status) => {
    const badges = {
      completed: { text: '✓ 已完成', style: styles.badgeSuccess },
      failed: { text: '✗ 失败', style: styles.badgeError },
      in_progress: { text: '⟳ 进行中', style: styles.badgeWarning },
      pending: { text: '⏳ 等待中', style: styles.badgeWarning },
      timeout: { text: '⏱️ 超时', style: styles.badgeError }
    };
    const badge = badges[status] || { text: status, style: {} };
    return <span style={{ ...styles.badge, ...badge.style }}>{badge.text}</span>;
  };

  return (
    <div style={{ ...styles.card, marginTop: '20px' }}>
      <h4 style={{ fontSize: '1.1rem', marginBottom: '15px' }}>
        轨迹详情：{trajectory.task_id}
      </h4>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>状态</span>
        {getStatusBadge(trajectory.status)}
      </div>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>耗时</span>
        <span style={styles.metricValue}>{(trajectory.total_duration_ms / 1000).toFixed(1)}秒</span>
      </div>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>步骤数</span>
        <span style={styles.metricValue}>{trajectory.num_steps}</span>
      </div>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>LLM 调用次数</span>
        <span style={styles.metricValue}>{trajectory.num_llm_calls}</span>
      </div>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>工具调用次数</span>
        <span style={styles.metricValue}>{trajectory.num_tool_calls}</span>
      </div>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>合理性得分</span>
        <span style={{ ...styles.metricValue, ...getScoreClass(trajectory.trajectory_rationality_score) }}>
          {trajectory.trajectory_rationality_score.toFixed(1)}/100
        </span>
      </div>

      <div style={styles.metricRow}>
        <span style={styles.metricLabel}>效率得分</span>
        <span style={{ ...styles.metricValue, ...getScoreClass(trajectory.trajectory_efficiency_score) }}>
          {trajectory.trajectory_efficiency_score.toFixed(1)}/100
        </span>
      </div>
    </div>
  );
};

/**
 * 主仪表盘组件
 */
const EvaluationDashboard = () => {
  const [writehereEval, setWritehereEval] = useState(null);
  const [moShenEval, setMoShenEval] = useState(null);
  const [selectedTrajectory, setSelectedTrajectory] = useState(null);
  const [loading, setLoading] = useState(true);

  // 从 API 加载评估数据
  useEffect(() => {
    const loadEvaluations = async () => {
      try {
        // 这里应该调用后端 API 获取评估数据
        // const response = await fetch('/api/evaluations');
        // const data = await response.json();

        // 模拟数据（实际使用时删除）
        setTimeout(() => {
          setWritehereEval({
            evaluation_id: 'eval_writehere_20260624_143022',
            agent_type: 'writehere',
            overall_step_level_score: 87.5,
            overall_trajectory_level_score: 82.3,
            llm_call_accuracy: 92.0,
            tool_call_accuracy: 88.5,
            parameter_format_accuracy: 95.0,
            response_parse_accuracy: 90.0,
            avg_rationality_score: 85.0,
            avg_efficiency_score: 79.6,
            trajectory_success_rate: 88.9,
            avg_trajectory_duration_ms: 45000,
            total_trajectories: 9,
            identified_issues: ['部分轨迹耗时较长'],
            improvement_suggestions: ['优化长耗时步骤']
          });

          setMoShenEval({
            evaluation_id: 'eval_mo_shen_20260624_143155',
            agent_type: 'mo_shen',
            overall_step_level_score: 91.2,
            overall_trajectory_level_score: 88.7,
            llm_call_accuracy: 95.5,
            tool_call_accuracy: 93.0,
            parameter_format_accuracy: 97.0,
            response_parse_accuracy: 94.0,
            avg_rationality_score: 90.0,
            avg_efficiency_score: 87.4,
            trajectory_success_rate: 94.4,
            avg_trajectory_duration_ms: 38000,
            total_trajectories: 9,
            identified_issues: [],
            improvement_suggestions: []
          });

          setLoading(false);
        }, 1000);
      } catch (error) {
        console.error('加载评估数据失败:', error);
        setLoading(false);
      }
    };

    loadEvaluations();
  }, []);

  if (loading) {
    return (
      <div style={{ ...styles.container, textAlign: 'center', paddingTop: '100px' }}>
        <div style={{ fontSize: '2rem', color: '#667eea' }}>加载中...</div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* 头部 */}
      <header style={styles.header}>
        <h1 style={styles.title}>🎯 Agent 能力评估系统</h1>
        <p style={styles.subtitle}>
          WriteHERE vs Mo-Shen - 企业文档生产 Agent 对比分析
        </p>
      </header>

      {/* 总体评分卡片 */}
      <section style={styles.section}>
        <h2 style={{ fontSize: '1.8rem', marginBottom: '20px', color: '#374151' }}>
          总体评分
        </h2>
        <div style={styles.grid}>
          <AgentCard
            agentType="writehere"
            evaluation={writehereEval}
            onClick={() => writehereEval && setSelectedTrajectory(writehereEval.trajectories?.[0])}
          />
          <AgentCard
            agentType="mo_shen"
            evaluation={moShenEval}
            onClick={() => moShenEval && setSelectedTrajectory(moShenEval.trajectories?.[0])}
          />
        </div>
      </section>

      {/* 详细对比 */}
      <section style={styles.section}>
        <ComparisonTable writehereEval={writehereEval} moShenEval={moShenEval} />
      </section>

      {/* 问题与建议 */}
      <section style={{ ...styles.section, ...styles.grid }}>
        <IssuesAndSuggestions evaluation={writehereEval} agentType="writehere" />
        <IssuesAndSuggestions evaluation={moShenEval} agentType="mo_shen" />
      </section>

      {/* 轨迹详情（如果有选中的） */}
      {selectedTrajectory && (
        <section style={styles.section}>
          <button
            onClick={() => setSelectedTrajectory(null)}
            style={{ ...styles.button, ...styles.secondaryButton, marginBottom: '20px' }}
          >
            ← 返回总览
          </button>
          <TrajectoryDetails trajectory={selectedTrajectory} />
        </section>
      )}

      {/* 使用说明 */}
      <section style={{ ...styles.card, background: '#f9fafb' }}>
        <h3 style={styles.cardTitle}>📊 评估标准说明</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px' }}>
          <div>
            <h4 style={{ fontSize: '1.1rem', color: '#667eea', marginBottom: '10px' }}>
              单步评估（Step-level）
            </h4>
            <ul style={{ paddingLeft: '20px', color: '#4b5563', lineHeight: '1.8' }}>
              <li>LLM 调用正确性（参数、格式）</li>
              <li>工具调用正确性（执行、输出）</li>
              <li>响应解析成功率</li>
              <li>单步耗时效率</li>
            </ul>
          </div>
          <div>
            <h4 style={{ fontSize: '1.1rem', color: '#667eea', marginBottom: '10px' }}>
              轨迹评估（Trajectory-level）
            </h4>
            <ul style={{ paddingLeft: '20px', color: '#4b5563', lineHeight: '1.8' }}>
              <li>整体流程合理性</li>
              <li>步骤序列效率</li>
              <li>资源利用率</li>
              <li>错误处理能力</li>
            </ul>
          </div>
          <div>
            <h4 style={{ fontSize: '1.1rem', color: '#667eea', marginBottom: '10px' }}>
              任务完成度（Task Completion）
            </h4>
            <ul style={{ paddingLeft: '20px', color: '#4b5563', lineHeight: '1.8' }}>
              <li>最终输出质量（手动评估）</li>
              <li>需求满足程度</li>
              <li>内容准确性</li>
              <li>创造性与连贯性</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
};

export default EvaluationDashboard;
