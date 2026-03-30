package tests

import (
	"testing"

	"github.com/Tencent/WeKnora/internal/infrastructure/chunker"
	"github.com/Tencent/WeKnora/internal/searchutil"
)

func TestSensitiveFilter(t *testing.T) {
	// 测试文本
	testText := "这是一个包含敏感信息的文本，比如密码：123456，身份证：123456789012345678，以及手机号：13800138000"

	// 脱敏配置
	sensitiveConfig := searchutil.SensitiveConfig{
		Enabled: true,
		Replacements: map[string]string{
			"123456":      "******",
			"123456789012345678": "****************",
			"13800138000": "***********",
		},
	}

	// 应用脱敏过滤
	treatedText := searchutil.ApplySensitiveFilter(testText, sensitiveConfig)

	// 验证脱敏结果
	expected := "这是一个包含敏感信息的文本，比如密码：******，身份证：****************，以及手机号：***********"
	if treatedText != expected {
		t.Errorf("脱敏结果不符合预期，got: %s, want: %s", treatedText, expected)
	}
}

func TestSplitTextWithSensitiveFilter(t *testing.T) {
	// 测试文本
	testText := "这是一个包含敏感信息的文本，比如密码：123456，身份证：123456789012345678，以及手机号：13800138000"

	// 脱敏配置
	sensitiveConfig := searchutil.SensitiveConfig{
		Enabled: true,
		Replacements: map[string]string{
			"123456":      "******",
			"123456789012345678": "****************",
			"13800138000": "***********",
		},
	}

	// 切片配置
	chunkConfig := chunker.SplitterConfig{
		ChunkSize:    100,
		ChunkOverlap: 20,
		Separators:   []string{"，", "。"},
	}

	// 使用带脱敏功能的切片函数
	chunks := chunker.SplitTextWithSensitiveFilter(testText, chunkConfig, sensitiveConfig)

	// 验证切片结果
	if len(chunks) == 0 {
		t.Error("切片结果为空")
		return
	}

	// 验证脱敏是否生效
	for i, chunk := range chunks {
		if chunk.Content == "" {
			t.Errorf("第 %d 个 chunk 内容为空", i)
		}
		// 验证敏感信息是否被脱敏
		if chunk.Content == "123456" || chunk.Content == "123456789012345678" || chunk.Content == "13800138000" {
			t.Errorf("第 %d 个 chunk 中包含未脱敏的敏感信息", i)
		}
	}
}
