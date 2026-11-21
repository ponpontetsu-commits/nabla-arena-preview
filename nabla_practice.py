"""NABLA ARENA practice room: no timer, no CPU, unlimited selectable cards.
Uses the SAME play() maths and foul decisions as normal matches. No persistence.
"""
from __future__ import annotations
from copy import deepcopy
from collections import OrderedDict
from nabla_game import new_game, play, FUNCTIONS
from nabla_math import proportional_on_shared_domain

MAX_NODES=200
MAX_BASES=24


def _board(p):
    return {'name':p['name'], 'bases':deepcopy(p['bases']), 'dimension':len(p['bases'])}


def _compact(game):
    return {'players':[_board(p) for p in game['players']],
            'history':deepcopy(game.get('history', [])),
            'finished':bool(game.get('finished')),
            'winner':game.get('winner'),
            'end_reason':game.get('end_reason')}


class Practice:
    def __init__(self, left=None, right=None):
        game=new_game()
        game['deck']=['one']*120
        game['history']=[]
        for seat,choices in enumerate((left,right)):
            if choices is None:
                choices=['one','x','x2']
            if not isinstance(choices,list) or len(choices)>MAX_BASES:
                raise ValueError('初期基底の数が不正です。')
            game['players'][seat]['bases']=[]
            game['players'][seat]['next_basis_id']=1
            game['players'][seat]['name']='練習盤面 '+('A' if seat==0 else 'B')
            for code in choices:
                self._insert(game,seat,code)
        self.nodes=OrderedDict()
        self.current='0'
        self.next_id=1
        self.nodes['0']={'parent':None,'label':'練習開始','game':game}

    def _insert(self,game,seat,code,number=None):
        if code not in FUNCTIONS:
            raise ValueError('一覧にない基底です。')
        expr=FUNCTIONS[code]
        if code=='zero':
            raise ValueError('0は独立した基底として追加できません。')
        board=game['players'][seat]['bases']
        if len(board)>=MAX_BASES:
            raise ValueError('基底数の上限を超えました。')
        for other in board:
            dep=proportional_on_shared_domain(expr,other['expression'])
            if dep=='yes':
                raise ValueError('線形従属する基底は追加できません。')
            if dep=='unsupported':
                raise ValueError('基底の線形独立性を厳密に確認できません。')
        if number is None:
            number=game['players'][seat]['next_basis_id']
            game['players'][seat]['next_basis_id']=number+1
        board.append({'id':number,'expression':expr})

    def view(self):
        node=self.nodes[self.current]
        return {'active':True,'current_node':self.current,
                'nodes':[{'id':key,'parent':value['parent'],'label':value['label']}
                         for key,value in self.nodes.items()],
                **_compact(node['game'])}

    def _commit(self,game,label):
        if len(self.nodes)>=MAX_NODES:
            raise ValueError('履歴は最大200状態です。過去の状態を整理してください。')
        key=str(self.next_id)
        self.next_id+=1
        self.nodes[key]={'parent':self.current,'label':label,'game':game}
        self.current=key
        return {'ok':True,'state':self.view()}

    def restore(self,node):
        if str(node) not in self.nodes:
            return {'ok':False,'message':'復元先の状態が見つかりません。'}
        self.current=str(node)
        return {'ok':True,'state':self.view()}

    def reset(self,mode):
        if mode=='initial':
            self.current='0'
        elif mode=='empty':
            old=deepcopy(self.nodes[self.current]['game'])
            for p in old['players']:
                p['bases']=[]
                p['next_basis_id']=1
            old['history']=[]
            old['finished']=False
            old['end_reason']=None
            old['winner']=None
            self.nodes=OrderedDict({'0':{'parent':None,'label':'空の初期盤面','game':old}})
            self.current='0';self.next_id=1
        elif mode=='set_initial':
            old=deepcopy(self.nodes[self.current]['game'])
            old['history']=[]
            old['finished']=False
            old['end_reason']=None
            old['winner']=None
            self.nodes=OrderedDict({'0':{'parent':None,'label':'保存した初期盤面','game':old}})
            self.current='0';self.next_id=1
        else:
            return {'ok':False,'message':'リセット方法が不正です。'}
        return {'ok':True,'state':self.view()}

    def edit(self,data):
        seat=data.get('seat')
        operation=data.get('operation')
        if type(seat) is not int or seat not in (0,1):
            return {'ok':False,'message':'盤面が不正です。'}
        game=deepcopy(self.nodes[self.current]['game'])
        board=game['players'][seat]['bases']
        try:
            if operation=='add':
                self._insert(game,seat,data.get('code'))
            elif operation in ('remove','replace'):
                number=data.get('basis_id')
                matches=[b for b in board if b['id']==number]
                if len(matches)!=1:
                    raise ValueError('対象の基底が存在しません。')
                board[:]=[b for b in board if b['id']!=number]
                if operation=='replace':
                    self._insert(game,seat,data.get('code'),number)
                    board.sort(key=lambda b:b['id'])
            else:
                raise ValueError('編集方法が不正です。')
        except ValueError as exc:
            return {'ok':False,'message':str(exc)}
        game['finished']=False
        game['winner']=None
        game['end_reason']=None
        return self._commit(game, f'盤面{seat+1}を手動編集：{operation}')

    def operate(self,data):
        actor=data.get('actor',0)
        target=data.get('target_player')
        codes=data.get('cards',[])
        if type(actor) is not int or actor not in (0,1) or type(target) is not int or target not in (0,1):
            return {'ok':False,'message':'プレイヤー指定が不正です。'}
        if not isinstance(codes,list) or not 1<=len(codes)<=18 or any(c not in {**FUNCTIONS,**{
             'diff':1,'integrate':1,'all_diff':1,'all_diff2':1,
             'mul':1,'div':1,'limit_zero':1,'limit_plus_inf':1,
             'limit_minus_inf':1,'limsup_plus_inf':1,'liminf_plus_inf':1,
             'sqrt':1,'inverse':1,'log':1}} for c in codes):
            return {'ok':False,'message':'カードの指定が不正です。'}
        game=deepcopy(self.nodes[self.current]['game'])
        game['current']=actor
        game['finished']=False
        game['winner']=None
        game['end_reason']=None
        game['players'][actor]['hand']=codes[:]
        game['deck']=['one']*120
        action={'kind':'add' if codes[0] in FUNCTIONS else 'operate',
                'card_indices':list(range(len(codes))),
                'target_player':target}
        if type(data.get('basis_id')) is int:
            action['basis_id']=data['basis_id']
        if data.get('branch') is not None:
            action['branch']=data['branch']
        outcome=play(game,actor,action,expected_revision=game['revision'])
        if outcome['status']=='foul':
            return {'ok':False,'status':'foul','message':outcome['reason'],
                    'retry':True,'state':self.view()}
        if outcome['status']!='ok':
            return {'ok':False,'status':outcome['status'],
                    'message':outcome.get('reason','処理できません。'),
                    'branch_options':outcome.get('branch_options',[]),
                    'state':self.view()}
        new_state=outcome['state']
        new_state['deck']=['one']*120
        for player in new_state['players']:
            player['hand']=[]
        # A practice session may inspect the defeat and then restore a prior
        # node or edit bases. It never alters ordinary match adjudication.
        label=' → '.join(codes)+'：盤面'+str(target+1)
        return self._commit(new_state,label)


def dispatch(state,path,data):
    key=path.rsplit('/',1)[-1]
    if key=='start':
        try:
            state['practice']=Practice(data.get('left'),data.get('right'))
            return {'ok':True,'state':state['practice'].view()}
        except ValueError as exc:
            return {'ok':False,'message':str(exc)}
    if key=='close':
        state.pop('practice',None)
        return {'ok':True}
    room=state.get('practice')
    if room is None:
        return {'ok':False,'message':'練習モードが開始されていません。'}
    if key=='state':
        return {'ok':True,'state':room.view()}
    if key=='restore':
        return room.restore(data.get('node'))
    if key=='reset':
        return room.reset(data.get('mode'))
    if key=='edit':
        return room.edit(data)
    if key=='operate':
        return room.operate(data)
    return {'ok':False,'message':'未対応の練習操作です。'}
