package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"runtime"
	"strings"
	"time"
)

const agentVersion = "0.1.0"

type Config struct {
	BackendURL string
	Token      string
	MachineID  string
	Hostname   string
}

type Command struct {
	ID            int    `json:"id"`
	Type          string `json:"type"`
	ExamID        string `json:"exam_id"`
	AssignmentID  int    `json:"assignment_id"`
	StudentNumber string `json:"student_number"`
	MachineID     string `json:"machine_id"`
}

type CommandResponse struct {
	Command *Command `json:"command"`
}

type ExamConfig struct {
	ExamID   string `json:"exam_id"`
	Filename string `json:"filename"`
	Content  string `json:"content"`
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("SecureExam Agent %s", agentVersion)
	log.Printf("machine_id = %s", cfg.MachineID)
	log.Printf("backend    = %s", cfg.BackendURL)

	err = postJSON(
		cfg,
		"/agent/register",
		map[string]any{
			"machine_id": cfg.MachineID,
			"hostname":   cfg.Hostname,
			"os_name":    runtime.GOOS,
			"version":    agentVersion,
		},
		nil,
	)

	if err != nil {
		log.Fatalf("register: %v", err)
	}

	state := "IDLE"
	log.Printf("state -> %s", state)

	for {
		if err := heartbeat(cfg, state); err != nil {
			log.Printf("heartbeat error: %v", err)
		}

		var response CommandResponse

		err := getJSON(
			cfg,
			"/agent/commands/"+
				cfg.MachineID+
				"/next",
			&response,
		)

		if err != nil {
			log.Printf("poll error: %v", err)
			time.Sleep(3 * time.Second)
			continue
		}

		if response.Command == nil {
			time.Sleep(3 * time.Second)
			continue
		}

		cmd := response.Command

		log.Printf(
			"command #%d -> %s exam=%s student=%s",
			cmd.ID,
			cmd.Type,
			cmd.ExamID,
			cmd.StudentNumber,
		)

		if cmd.Type != "START_EXAM" {
			_ = complete(
				cfg,
				cmd.ID,
				"ERROR",
				"Commande inconnue",
			)

			state = "ERROR"
			continue
		}

		state = "CHECKING"
		log.Printf("state -> %s", state)
		_ = heartbeat(cfg, state)

		var examConfig ExamConfig

		err = getJSON(
			cfg,
			"/agent/config/"+cmd.ExamID,
			&examConfig,
		)

		if err != nil {
			log.Printf("config error: %v", err)

			_ = complete(
				cfg,
				cmd.ID,
				"ERROR",
				err.Error(),
			)

			state = "ERROR"
			continue
		}

		if strings.TrimSpace(
			examConfig.Content,
		) == "" {
			_ = complete(
				cfg,
				cmd.ID,
				"ERROR",
				"Configuration NixOS vide",
			)

			state = "ERROR"
			continue
		}

		log.Printf(
			"config received: %s (%d bytes)",
			examConfig.Filename,
			len(examConfig.Content),
		)

		state = "PREPARING"
		log.Printf("state -> %s", state)
		_ = heartbeat(cfg, state)

		/*
		   V1 WINDOWS :
		   on simule seulement l'application NixOS.

		   Prochaine version Linux :
		   CHECKING
		   -> PREPARE
		   -> nixos-rebuild
		   -> VERIFY
		   -> READY
		*/

		time.Sleep(5 * time.Second)

		err = complete(
			cfg,
			cmd.ID,
			"DONE",
			"SIMULATED_READY",
		)

		if err != nil {
			log.Printf(
				"complete error: %v",
				err,
			)

			state = "ERROR"
			continue
		}

		state = "READY"

		log.Printf("state -> READY")
		log.Printf(
			"exam %s READY (simulation V1)",
			cmd.ExamID,
		)
	}
}

func loadConfig() (Config, error) {
	backend := strings.TrimRight(
		strings.TrimSpace(
			os.Getenv(
				"SECUREEXAM_BACKEND_URL",
			),
		),
		"/",
	)

	if backend == "" {
		backend = "http://127.0.0.1:8000"
	}

	token := strings.TrimSpace(
		os.Getenv(
			"SECUREEXAM_AGENT_TOKEN",
		),
	)

	if token == "" {
		return Config{},
			errors.New(
				"SECUREEXAM_AGENT_TOKEN manquant",
			)
	}

	machineID := strings.TrimSpace(
		os.Getenv(
			"SECUREEXAM_MACHINE_ID",
		),
	)

	if machineID == "" {
		machineID = detectMachineID()
	}

	if machineID == "" {
		return Config{},
			errors.New(
				"machine_id introuvable",
			)
	}

	hostname, _ := os.Hostname()

	return Config{
		BackendURL: backend,
		Token:      token,
		MachineID:  machineID,
		Hostname:   hostname,
	}, nil
}

func detectMachineID() string {
	if runtime.GOOS == "linux" {
		data, err := os.ReadFile(
			"/etc/machine-id",
		)

		if err == nil {
			value := strings.TrimSpace(
				string(data),
			)

			if value != "" {
				return value
			}
		}
	}

	hostname, _ := os.Hostname()

	hostname = strings.TrimSpace(
		hostname,
	)

	if hostname == "" {
		return ""
	}

	return "DEV-" +
		strings.ToUpper(
			hostname,
		)
}

func heartbeat(
	cfg Config,
	state string,
) error {
	return postJSON(
		cfg,
		"/agent/heartbeat",
		map[string]any{
			"machine_id": cfg.MachineID,
			"state":      state,
		},
		nil,
	)
}

func complete(
	cfg Config,
	commandID int,
	status string,
	message string,
) error {
	return postJSON(
		cfg,
		fmt.Sprintf(
			"/agent/commands/%d/complete",
			commandID,
		),
		map[string]any{
			"machine_id": cfg.MachineID,
			"status":     status,
			"message":    message,
		},
		nil,
	)
}

func getJSON(
	cfg Config,
	path string,
	out any,
) error {
	req, err := http.NewRequest(
		http.MethodGet,
		cfg.BackendURL+path,
		nil,
	)

	if err != nil {
		return err
	}

	return execute(
		cfg,
		req,
		out,
	)
}

func postJSON(
	cfg Config,
	path string,
	body any,
	out any,
) error {
	payload, err := json.Marshal(body)

	if err != nil {
		return err
	}

	req, err := http.NewRequest(
		http.MethodPost,
		cfg.BackendURL+path,
		bytes.NewReader(payload),
	)

	if err != nil {
		return err
	}

	req.Header.Set(
		"Content-Type",
		"application/json",
	)

	return execute(
		cfg,
		req,
		out,
	)
}

func execute(
	cfg Config,
	req *http.Request,
	out any,
) error {
	req.Header.Set(
		"X-SecureExam-Agent-Token",
		cfg.Token,
	)

	req.Header.Set(
		"ngrok-skip-browser-warning",
		"1",
	)

	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	resp, err := client.Do(req)

	if err != nil {
		return err
	}

	defer resp.Body.Close()

	data, err := io.ReadAll(
		io.LimitReader(
			resp.Body,
			10*1024*1024,
		),
	)

	if err != nil {
		return err
	}

	if resp.StatusCode < 200 ||
		resp.StatusCode >= 300 {
		return fmt.Errorf(
			"HTTP %d: %s",
			resp.StatusCode,
			strings.TrimSpace(
				string(data),
			),
		)
	}

	if out == nil || len(data) == 0 {
		return nil
	}

	if err := json.Unmarshal(
		data,
		out,
	); err != nil {
		return fmt.Errorf(
			"JSON invalide: %w",
			err,
		)
	}

	return nil
}
