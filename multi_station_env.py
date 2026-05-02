import gymnasium as gym
from gymnasium import spaces
import numpy as np
from hw_communication import RaspberryPiInterface

class MultiStationChargingEnv(gym.Env):
    """실물 1개 + 시뮬레이션 4개 보드가 연동된 다중 전기차 충전소 환경"""
    
    def __init__(self, num_stations=5, num_chargers = 5, use_hardware=True):
        super().__init__()
        self.num_stations = num_stations # 총 5개 (실물 1 + 가상 4)
        self.use_hardware = use_hardware
        self.num_chargers = num_chargers
        self.p_per_charger = 7.0        # 충전기 1대당 소모 전력 (1kW)
        
        # --- 하드웨어 인터페이스 초기화 ---
        if self.use_hardware:
            self.pi_interface = RaspberryPiInterface(pi_ip="192.168.219.114")
        
        # --- 하드 제약 및 설비 한계 ---
        self.e_c = np.full(self.num_stations, 998.0) # ESS 최대 용량
        self.soc_min = 0.1 # 현재 충전 상태 최소
        self.soc_max = 0.9 # 현재 충전 상태 최대
        self.e_ch_max = 90.0 # ESS의 최대 충전률
        self.e_dis_max = 90.0 # ESS의 최대 방전률
        self.P_line_max = 50.0 # 
        
        # --- 비용/보상 가중치 ---
        self.lam_g = 1.0        # 전력망(Grid) 요금
        self.lam_tr = 0.1       # 
        self.lam_unserved = 5.0 
        self.lam_s = 2.0        

        # --- Action Space ---
        total_actions = self.num_stations * 2 + (self.num_stations ** 2)    
        # ESS 충/방전 5개 + Grid 전력 구매 5개 + 스테이션 간 전력 전송 5x5 개 = 총 35개의 행동
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(total_actions,), dtype=np.float32)
        
        # --- Observation Space ---
        # SoC 5개 + 수요 (v, 5개) + PV 발전량 (p, 5개) + TOU 요금 1개 + 충전기 플래그 (5개소 * 5개 = 25)
        total_obs = self.num_stations * 3 + 1 + (self.num_stations * self.num_chargers)
        self.observation_space = spaces.Box(low=0.0, high=np.inf, shape=(total_obs,), dtype=np.float32)
        
        self.current_step = 0   # 이 환경은 하루 24시간을 기준으로 1시간 단위로 돌아감
        self.max_steps = 24     # step() 한 번 할 때마다 스텝 증가
        
        self.dataset_pv = None  # 외부에서 데이터셋 받아올거라면 pv, flags, tou 등의 데이터를 담아두는 공간
        self.dataset_flags = None
        self.dataset_tou = None

    def _generate_mock_dataset(self):
        """24시간 임의 데이터셋 생성 (나중에 pandas로 교체 가능)"""
        # ToU 요금: 논문 기반 (84.5, 111.9, 174.0) 
        tou = np.array([84.5]*8 + [111.9]*5 + [174.0]*5 + [111.9]*6, dtype=np.float32)
        
        # PV 및 수요 데이터 생성. 나중에는 정해진 데이터셋으로 할 예정
        pv = np.zeros((self.max_steps, self.num_stations), dtype=np.float32)
        for t in range(8, 19):
            pv[t, :] = np.random.uniform(20.0, 100.0, self.num_stations) * np.sin(np.pi * (t - 8) / 10)
            # 태양은 정오에 가장 강하고 점점 떨어짐. 이를 sin 함수 형태로 구현
            # 20-100 사이의 실수 5개 생성하라는 뚯. 8-18시 까지의 시간에만 태양열 발전을 한다는 가정하에 만듦.
        
        # 각 시간(24) / 스테이션(5) / 충전기(5) 별 수요 플래그 생성 (0 또는 1)
        # 낮 시간(9~20시)에 수요가 더 많도록 설정
        charger_flags = np.random.choice([0, 1], size=(self.max_steps, self.num_stations, self.num_chargers), p=[0.7, 0.3])
        charger_flags[9:21, :, :] = np.random.choice([0, 1], size=(12, self.num_stations, self.num_chargers), p=[0.4, 0.6])
        
        return pv, charger_flags.astype(np.float32), tou
    
    def _update_current_state_vars(self):
        t = self.current_step
        if t < self.max_steps:
            self.current_pv = self.dataset_pv[t]
            self.current_flags = self.dataset_flags[t] # [5, 5] 행렬
            self.current_ToU = np.array([self.dataset_tou[t]], dtype=np.float32)
            
            # --- 충전기 플래그를 기반으로 총 수요(p_load) 계산 ---
            # 각 스테이션별로 'True(1)'인 개수만큼 전력을 소모한다고 가정
            self.current_v = np.sum(self.current_flags, axis=1) * self.p_per_charger

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.dataset_pv, self.dataset_flags, self.dataset_tou = self._generate_mock_dataset()
        self.soc = np.random.uniform(self.soc_min, self.soc_max, self.num_stations).astype(np.float32)
        
        self._update_current_state_vars()
        return self._get_obs(), {}

    def step(self, action):
        N = self.num_stations
        
        # 1. 행동 분해
        a_ess = action[0 : N] # ESS 충방전을 얼마나 할까? -1~1 사이의 값으로 세팅
        a_grid = np.clip(action[N : 2*N], 0.0, 1.0)  # 반드시 0-1 사이의 값으로 고정, 외부 전력망에서 전기를 얼마나 사올까?
        a_tr_matrix = np.clip(action[2*N :], 0.0, 1.0).reshape((N, N)) # 스테이션 간 전력 전송을 얼마나 할까? 이를 0-1 사이의 값으로 클립하고 5x5 형태로 
        np.fill_diagonal(a_tr_matrix, 0.0) # 5x5 행렬의 대각선을 0으로 채움으로써 자기 자신에게 전송을 금지함.
        
        # 2. 하드 제약 기반 SoC 업데이트 
        ess_energy_change = a_ess * np.where(a_ess > 0, self.e_ch_max, self.e_dis_max)
        # a_ess는 AI가 준 행동. 여기에 a_ess>0인 부분에는 최대 충전 속도를 곱해 실제 충전량을, a_ess<0인 부분에는 최대 방전 속도를 곱해 실제 방전량을 구함
        new_soc = self.soc + (ess_energy_change / self.e_c)
        # 에너지 변화량을 바탕으로 새로운 SoC를 계산해냄. 이때 식은 새로운 SoC = 기존 SoC + (실제 충,방전 량 / 전체 에너지 용량)
        new_soc_clipped = np.clip(new_soc, self.soc_min, self.soc_max)
        # rule-based 안전 장치. 새로운 SoC를 최소, 최대 soc 기준으로 클리핑
        actual_ess_energy = (new_soc_clipped - self.soc) * self.e_c     # 클리핑을 고려한 실제 에너지 변화량
        
        self.soc = new_soc_clipped  # SoC 업데이트

        # --- 실물 하드웨어 통신 및 LED 제어 ---
        if self.use_hardware:
            # 0번 충전소의 결정에 따라 LED 색상 결정
            led_status = "OFF"
            if a_ess[0] > 0:      # 충전 시 (Positive)
                led_status = "BLUE"
            elif a_ess[0] < 0:   # 방전 시 (Negative)
                led_status = "RED"
            
            # 라즈베리 파이로 명령 전송, 통신 클래스에 send_action_with_led가 구현되어 있다고 가정
            self.pi_interface.send_action_to_pi(
                a_ess=a_ess[0], 
                led_color=led_status
            )
            
            # 실제 보드에서 SoC 값을 읽어와 동기화 (선택 사항)
            real_soc, _ = self.pi_interface.read_state_from_pi()
            if real_soc is not None:
                self.soc[0] = real_soc

        # 3. 전력망 흐름 및 보상 계산 (모든 5개 스테이션 대상, 만약 RL 측에서 필요할 시 구현)
        total_reward = 0.0
        for i in range(N):
            grid_import = a_grid[i] * 200.0    # 얼마나 외부 전력망에서 사왔는지. 최대 200kW
            transfer_out = np.sum(a_tr_matrix[i, :] * self.P_line_max)  # 얼마나 나갈지. P_line_max는 전선이 버틸 수 있는 최대 용량
            # 여기서 [i, :]이란, i 행의 모든 열을 가져와라
            transfer_in = np.sum(a_tr_matrix[:, i] * self.P_line_max)   # 얼마나 들어올지
            # 여기서 [:, i]란, i 열의 모든 행을 가져와라
            
            # 에너지 밸런스 계산 
            available_power = self.current_pv[i] + grid_import + max(0, -actual_ess_energy[i]) + transfer_in - transfer_out
            supplied_power = min(max(available_power, 0), self.current_v[i])
            unserved_power = self.current_v[i] - supplied_power
            self_supplied = min(self.current_pv[i] + max(0, -actual_ess_energy[i]), supplied_power)

            # 보상 함수 
            cost_grid = grid_import * self.current_ToU[0] * self.lam_g
            cost_transfer = transfer_out * 5.0 * self.lam_tr 
            penalty_unserved = unserved_power * 100.0 * self.lam_unserved
            reward_self_supply = self_supplied * self.current_ToU[0] * self.lam_s
            
            total_reward += (reward_self_supply - cost_grid - cost_transfer - penalty_unserved)

        # 4. 시간 진행 및 종료 체크
        self.current_step += 1
        terminated = bool(self.current_step >= self.max_steps)
        truncated = False
        
        if not terminated:
            self._update_current_state_vars()
            
        return self._get_obs(), total_reward, terminated, truncated, {}

    def _get_obs(self):
        # 정규화 적용 (학습 효율 극대화)
        norm_soc = self.soc  # 이미 0~1 사이
        norm_pv = self.current_pv / 100.0
        norm_v = self.current_v / (self.num_chargers * self.p_per_charger)
        norm_tou = self.current_ToU / 200.0
        flat_flags = self.current_flags.flatten() 
        return np.concatenate((norm_soc, norm_pv, norm_v, norm_tou, flat_flags), dtype=np.float32)